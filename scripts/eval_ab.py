#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://127.0.0.1:8081/v1/chat/completions"
DEFAULT_MODEL = "Qwen3.5-9B-BF16.gguf"
DEFAULT_PROMPTS = Path(__file__).resolve().parent.parent / "eval" / "prompts_qwen35b_ab.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="A/B quality evaluation helper for local OpenAI-compatible models.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser(
        "capture",
        help="Run prompt pack against one model and save raw responses.",
    )
    capture.add_argument("--url", default=DEFAULT_URL, help="OpenAI-compatible /v1/chat/completions endpoint")
    capture.add_argument("--model", default=DEFAULT_MODEL, help="Model id to request")
    capture.add_argument("--prompts-file", default=str(DEFAULT_PROMPTS), help="JSONL prompt file")
    capture.add_argument("--output-dir", default="", help="Output directory (default: eval_runs/<timestamp>)")
    capture.add_argument("--capture-name", default="", help="Capture label (default: sanitized model name)")
    capture.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature (0.0 = low variance)")
    capture.add_argument("--max-tokens", type=int, default=512, help="Fallback max_tokens")
    capture.add_argument("--timeout", type=float, default=180.0, help="Per-request timeout seconds")
    capture.add_argument("--prompt-limit", type=int, default=0, help="Run only first N prompts")
    capture.add_argument("--sleep", type=float, default=0.0, help="Sleep between requests (seconds)")
    capture.add_argument("--warmup-runs", type=int, default=0, help="Warmup calls per prompt (discarded)")
    capture.add_argument("--measured-runs", type=int, default=1, help="Measured calls per prompt")

    pack = sub.add_parser(
        "pack",
        help="Build blind scoring packet from two capture files.",
    )
    pack.add_argument("--capture-a", required=True, help="Path to first capture JSONL")
    pack.add_argument("--capture-b", required=True, help="Path to second capture JSONL")
    pack.add_argument("--output-dir", default="", help="Output directory (default: eval_runs/pack_<timestamp>)")
    pack.add_argument("--seed", type=int, default=42, help="Seed for per-prompt response slot randomization")
    return parser.parse_args()


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def make_output_dir(path_value: str, prefix: str) -> Path:
    if path_value:
        out = Path(path_value).expanduser().resolve()
    else:
        out = (Path.cwd() / "eval_runs" / f"{prefix}_{now_stamp()}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "capture"


def as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_prompts(path_value: str, limit: int) -> list[dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    prompts: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{lineno}: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"Expected JSON object at {path}:{lineno}")
            prompt_id = str(item.get("id") or "").strip()
            prompt_text = str(item.get("prompt") or "").strip()
            if not prompt_id or not prompt_text:
                raise ValueError(f"Prompt requires id + prompt at {path}:{lineno}")
            prompts.append(
                {
                    "id": prompt_id,
                    "category": str(item.get("category") or "general").strip() or "general",
                    "prompt": prompt_text,
                    "max_tokens": as_int(item.get("max_tokens") or 0),
                }
            )
            if limit > 0 and len(prompts) >= limit:
                break
    return prompts


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any], float]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
        status = int(response.status)
    elapsed = max(time.perf_counter() - started, 1e-6)
    decoded = json.loads(raw.decode("utf-8"))
    return status, decoded, elapsed


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def capture_once(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    started = now_iso_utc()
    try:
        http_status, data, elapsed = post_json(url, payload, timeout=timeout)
        error_text = ""
    except urllib.error.HTTPError as exc:
        elapsed = 0.0
        http_status = int(exc.code)
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            error_text = str(data.get("error", {}).get("message") or data.get("detail") or body[:240])
        except Exception:
            data = {}
            error_text = f"HTTP {exc.code}"
    except Exception as exc:
        elapsed = 0.0
        http_status = 0
        data = {}
        error_text = str(exc)

    usage = data.get("usage") if isinstance(data, dict) else {}
    timings = data.get("timings") if isinstance(data, dict) else {}

    content = ""
    model_reported = ""
    if isinstance(data, dict):
        model_reported = str(data.get("model") or "").strip()
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else {}
            if isinstance(message, dict):
                content = str(message.get("content") or "")
        if not error_text:
            error_obj = data.get("error")
            if isinstance(error_obj, dict):
                error_text = str(error_obj.get("message") or "").strip()

    prompt_tokens = as_int(usage.get("prompt_tokens"))
    completion_tokens = as_int(usage.get("completion_tokens"))
    gen_tps = as_float(timings.get("predicted_per_second"))
    prompt_tps = as_float(timings.get("prompt_per_second"))
    wall_tps = (completion_tokens / elapsed) if completion_tokens > 0 and elapsed > 0 else 0.0

    return {
        "captured_at": started,
        "http_status": http_status,
        "error": error_text,
        "content": content,
        "reported_model": model_reported,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": as_int(usage.get("total_tokens")),
        },
        "timings": {
            "prompt_per_second": prompt_tps,
            "predicted_per_second": gen_tps,
            "wall_tokens_per_second": wall_tps,
            "elapsed_seconds": elapsed,
        },
    }


def command_capture(args: argparse.Namespace) -> int:
    if args.warmup_runs < 0:
        print("--warmup-runs must be >= 0", file=sys.stderr)
        return 2
    if args.measured_runs < 1:
        print("--measured-runs must be >= 1", file=sys.stderr)
        return 2

    prompts = load_prompts(args.prompts_file, args.prompt_limit)
    if not prompts:
        print("No prompts loaded.", file=sys.stderr)
        return 2

    output_dir = make_output_dir(args.output_dir, "capture")
    capture_name = sanitize_name(args.capture_name or args.model)
    capture_path = output_dir / f"capture_{capture_name}.jsonl"
    metadata_path = output_dir / f"capture_{capture_name}.meta.json"

    print(f"Capture name: {capture_name}")
    print(f"URL:          {args.url}")
    print(f"Model:        {args.model}")
    print(f"Prompts:      {len(prompts)}")
    print(f"Warmup:       {args.warmup_runs} (discarded)")
    print(f"Measured:     {args.measured_runs}")
    print(f"Temperature:  {args.temperature}")
    print(f"Output:       {capture_path}")
    print()

    rows: list[dict[str, Any]] = []
    gen_tps_values: list[float] = []
    errors = 0
    measured_failures = 0

    for idx, prompt in enumerate(prompts, start=1):
        max_tokens = prompt["max_tokens"] if prompt["max_tokens"] > 0 else args.max_tokens
        payload = {
            "model": args.model,
            "stream": False,
            "temperature": args.temperature,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt["prompt"]}],
        }

        warmup_records: list[dict[str, Any]] = []
        measured_records: list[dict[str, Any]] = []

        for _ in range(args.warmup_runs):
            run = capture_once(args.url, payload, timeout=args.timeout)
            warmup_records.append(
                {
                    "http_status": as_int(run.get("http_status")),
                    "error": str(run.get("error") or ""),
                    "usage": run.get("usage") if isinstance(run.get("usage"), dict) else {},
                    "timings": run.get("timings") if isinstance(run.get("timings"), dict) else {},
                }
            )
            if args.sleep > 0:
                time.sleep(args.sleep)

        for run_index in range(1, args.measured_runs + 1):
            run = capture_once(args.url, payload, timeout=args.timeout)
            measured_records.append(
                {
                    "run": run_index,
                    "captured_at": str(run.get("captured_at") or ""),
                    "http_status": as_int(run.get("http_status")),
                    "error": str(run.get("error") or ""),
                    "content": str(run.get("content") or ""),
                    "reported_model": str(run.get("reported_model") or ""),
                    "usage": run.get("usage") if isinstance(run.get("usage"), dict) else {},
                    "timings": run.get("timings") if isinstance(run.get("timings"), dict) else {},
                }
            )
            if args.sleep > 0:
                time.sleep(args.sleep)

        successful_runs = [record for record in measured_records if not str(record.get("error") or "").strip()]
        measured_failures += len(measured_records) - len(successful_runs)

        source_runs = successful_runs if successful_runs else measured_records
        primary = source_runs[0]

        prompt_tokens_values = [as_int(record.get("usage", {}).get("prompt_tokens")) for record in source_runs]
        completion_tokens_values = [as_int(record.get("usage", {}).get("completion_tokens")) for record in source_runs]
        total_tokens_values = [as_int(record.get("usage", {}).get("total_tokens")) for record in source_runs]
        prompt_tps_values = [as_float(record.get("timings", {}).get("prompt_per_second")) for record in source_runs]
        gen_tps_per_run = [as_float(record.get("timings", {}).get("predicted_per_second")) for record in source_runs]
        wall_tps_values = [as_float(record.get("timings", {}).get("wall_tokens_per_second")) for record in source_runs]
        elapsed_values = [as_float(record.get("timings", {}).get("elapsed_seconds")) for record in source_runs]

        prompt_tokens = int(round(statistics.fmean(prompt_tokens_values))) if prompt_tokens_values else 0
        completion_tokens = int(round(statistics.fmean(completion_tokens_values))) if completion_tokens_values else 0
        total_tokens = int(round(statistics.fmean(total_tokens_values))) if total_tokens_values else 0
        prompt_tps = statistics.fmean(prompt_tps_values) if prompt_tps_values else 0.0
        gen_tps = statistics.fmean(gen_tps_per_run) if gen_tps_per_run else 0.0
        wall_tps = statistics.fmean(wall_tps_values) if wall_tps_values else 0.0
        elapsed = statistics.fmean(elapsed_values) if elapsed_values else 0.0

        row = {
            "captured_at": str(primary.get("captured_at") or ""),
            "capture_name": capture_name,
            "prompt_id": prompt["id"],
            "category": prompt["category"],
            "prompt": prompt["prompt"],
            "requested_model": args.model,
            "reported_model": str(primary.get("reported_model") or ""),
            "http_status": as_int(primary.get("http_status")),
            "error": str(primary.get("error") or ""),
            "content": str(primary.get("content") or ""),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "timings": {
                "prompt_per_second": prompt_tps,
                "predicted_per_second": gen_tps,
                "wall_tokens_per_second": wall_tps,
                "elapsed_seconds": elapsed,
            },
            "runs": {
                "warmup_count": args.warmup_runs,
                "measured_count": args.measured_runs,
                "successful_measured_count": len(successful_runs),
                "warmup": warmup_records,
                "measured": measured_records,
            },
        }
        rows.append(row)

        if not successful_runs:
            errors += 1
            print(f"[{idx:02d}/{len(prompts)}] {prompt['id']}: ERROR: {row['error']}")
        else:
            gen_tps_values.append(gen_tps)
            print(
                f"[{idx:02d}/{len(prompts)}] {prompt['id']}: "
                f"ok {len(successful_runs)}/{args.measured_runs} | "
                f"ctx {prompt_tokens} | tok {completion_tokens} | gen {gen_tps:.2f} tok/s"
            )

    write_jsonl(capture_path, rows)
    metadata = {
        "capture_name": capture_name,
        "created_at": now_iso_utc(),
        "url": args.url,
        "requested_model": args.model,
        "prompts_file": str(Path(args.prompts_file).expanduser().resolve()),
        "prompt_count": len(prompts),
        "error_count": errors,
        "warmup_runs_per_prompt": args.warmup_runs,
        "measured_runs_per_prompt": args.measured_runs,
        "temperature": args.temperature,
        "measured_failure_count": measured_failures,
        "mean_gen_tps": statistics.fmean(gen_tps_values) if gen_tps_values else 0.0,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"Wrote capture:  {capture_path}")
    print(f"Wrote metadata: {metadata_path}")
    print(f"Errors:         {errors}/{len(prompts)}")
    if gen_tps_values:
        print(f"Mean gen tps:   {statistics.fmean(gen_tps_values):.2f}")
    return 0


def load_capture(path_value: str) -> dict[str, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Capture file not found: {path}")
    out: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{lineno}: {exc}") from exc
            prompt_id = str(item.get("prompt_id") or "").strip()
            if not prompt_id:
                continue
            out.setdefault(prompt_id, item)
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def command_pack(args: argparse.Namespace) -> int:
    records_a = load_capture(args.capture_a)
    records_b = load_capture(args.capture_b)
    prompt_ids = sorted(set(records_a.keys()) & set(records_b.keys()))
    missing = sorted((set(records_a.keys()) ^ set(records_b.keys())))
    if not prompt_ids:
        print("No overlapping prompt ids between captures.", file=sys.stderr)
        return 2

    output_dir = make_output_dir(args.output_dir, "pack")
    blind_packet_path = output_dir / "blind_packet.md"
    blind_key_path = output_dir / "blind_key.csv"
    output_score_path = output_dir / "score_by_output.csv"
    pairwise_score_path = output_dir / "score_pairwise.csv"

    rng = random.Random(args.seed)
    blind_key_rows: list[dict[str, Any]] = []
    output_score_rows: list[dict[str, Any]] = []
    pairwise_rows: list[dict[str, Any]] = []

    md_lines: list[str] = []
    md_lines.append("# Blind A/B Scoring Packet")
    md_lines.append("")
    md_lines.append("Score without opening `blind_key.csv` first.")
    md_lines.append("")
    md_lines.append("Use `score_by_output.csv` and `score_pairwise.csv` for manual scoring.")
    md_lines.append("")

    for prompt_id in prompt_ids:
        rec_a = records_a[prompt_id]
        rec_b = records_b[prompt_id]
        slots = [("capture_a", rec_a), ("capture_b", rec_b)]
        rng.shuffle(slots)

        category = str(rec_a.get("category") or rec_b.get("category") or "general")
        prompt_text = str(rec_a.get("prompt") or rec_b.get("prompt") or "")
        md_lines.append(f"## {prompt_id} ({category})")
        md_lines.append("")
        md_lines.append("### Prompt")
        md_lines.append("")
        md_lines.append(prompt_text)
        md_lines.append("")

        for slot_index, (source_name, record) in enumerate(slots, start=1):
            slot_name = f"response_{slot_index}"
            content = str(record.get("content") or "").strip()
            if not content:
                content = f"[NO CONTENT] {record.get('error') or 'empty response'}"

            md_lines.append(f"### Response {slot_index}")
            md_lines.append("")
            md_lines.append(content)
            md_lines.append("")

            blind_key_rows.append(
                {
                    "prompt_id": prompt_id,
                    "category": category,
                    "response_slot": slot_name,
                    "source_capture": source_name,
                    "requested_model": str(record.get("requested_model") or ""),
                    "reported_model": str(record.get("reported_model") or ""),
                }
            )
            output_score_rows.append(
                {
                    "prompt_id": prompt_id,
                    "category": category,
                    "response_slot": slot_name,
                    "correctness_1_5": "",
                    "instruction_following_1_5": "",
                    "formatting_1_5": "",
                    "hallucination_control_1_5": "",
                    "overall_1_5": "",
                    "notes": "",
                }
            )

        pairwise_rows.append(
            {
                "prompt_id": prompt_id,
                "category": category,
                "preferred_response_slot": "",
                "confidence_1_5": "",
                "notes": "",
            }
        )

    blind_packet_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")

    write_csv(
        blind_key_path,
        blind_key_rows,
        [
            "prompt_id",
            "category",
            "response_slot",
            "source_capture",
            "requested_model",
            "reported_model",
        ],
    )
    write_csv(
        output_score_path,
        output_score_rows,
        [
            "prompt_id",
            "category",
            "response_slot",
            "correctness_1_5",
            "instruction_following_1_5",
            "formatting_1_5",
            "hallucination_control_1_5",
            "overall_1_5",
            "notes",
        ],
    )
    write_csv(
        pairwise_score_path,
        pairwise_rows,
        ["prompt_id", "category", "preferred_response_slot", "confidence_1_5", "notes"],
    )

    print(f"Wrote blind packet:        {blind_packet_path}")
    print(f"Wrote blind key:           {blind_key_path}")
    print(f"Wrote output score sheet:  {output_score_path}")
    print(f"Wrote pairwise score sheet:{pairwise_score_path}")
    if missing:
        print()
        print("Warning: prompt ids missing from one capture:")
        for prompt_id in missing:
            print(f"- {prompt_id}")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "capture":
        return command_capture(args)
    if args.command == "pack":
        return command_pack(args)
    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
