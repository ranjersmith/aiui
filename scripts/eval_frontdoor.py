#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://127.0.0.1:3390/v1/chat/completions"
DEFAULT_MODEL = "aiui-auto-router"
DEFAULT_PROMPTS = Path(__file__).resolve().parent.parent / "eval" / "frontdoor_regressions.jsonl"

LANE_HEADER_MAP = {
    "lane": "x-aiui-lane",
    "lane_contract_version": "x-aiui-lane-contract-version",
    "lane_policy": "x-aiui-lane-policy",
    "truth_standard": "x-aiui-truth-standard",
    "handoff_allowed": "x-aiui-handoff-allowed",
    "handoff_targets": "x-aiui-handoff-targets",
    "finish_reason": "x-aiui-finish-reason",
    "lane_path": "x-aiui-lane-path",
    "handoff_target": "x-aiui-handoff-target",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay front-door regression prompts against the orchestrator and score "
            "lane behavior plus prompt-specific expectations."
        ),
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="OpenAI-compatible /v1/chat/completions endpoint")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model id to request")
    parser.add_argument("--prompts-file", default=str(DEFAULT_PROMPTS), help="JSONL regression corpus")
    parser.add_argument("--output-dir", default="", help="Output directory (default: eval_runs/frontdoor_<timestamp>)")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--max-tokens", type=int, default=256, help="Fallback max_tokens")
    parser.add_argument("--timeout", type=float, default=180.0, help="Per-request timeout seconds")
    parser.add_argument("--prompt-limit", type=int, default=0, help="Run only first N prompts")
    parser.add_argument("--sleep", type=float, default=0.0, help="Sleep between prompts (seconds)")
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Always exit 0 even when one or more regression checks fail",
    )
    return parser.parse_args()


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def now_iso_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def make_output_dir(path_value: str) -> Path:
    if path_value:
        out = Path(path_value).expanduser().resolve()
    else:
        out = (Path.cwd() / "eval_runs" / f"frontdoor_{now_stamp()}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


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
                    "mode": str(item.get("mode") or "").strip().lower(),
                    "expect": item.get("expect") if isinstance(item.get("expect"), dict) else {},
                    "notes": str(item.get("notes") or "").strip(),
                }
            )
            if limit > 0 and len(prompts) >= limit:
                break
    return prompts


def build_payload(prompt: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "stream": False,
        "temperature": args.temperature,
        "max_tokens": prompt["max_tokens"] if prompt["max_tokens"] > 0 else args.max_tokens,
        "messages": [{"role": "user", "content": prompt["prompt"]}],
    }
    if prompt.get("mode"):
        payload["mode"] = prompt["mode"]
    return payload


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any], float, dict[str, str]]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        status = int(response.status)
        headers = {key.lower(): value for key, value in response.headers.items()}
    elapsed = max(time.perf_counter() - started, 1e-6)
    decoded = json.loads(raw.decode("utf-8"))
    return status, decoded, elapsed, headers


def extract_openai_content(body: dict[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except Exception:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "").strip() != "text":
                continue
            text = str(item.get("text") or "").strip()
            if text:
                parts.append(text)
        return " ".join(parts).strip()
    return str(content or "").strip()


def extract_finish_reason(body: dict[str, Any]) -> str:
    try:
        finish_reason = body["choices"][0]["finish_reason"]
    except Exception:
        return ""
    return str(finish_reason or "").strip()


def compile_patterns(items: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for item in items:
        compiled.append(re.compile(item))
    return compiled


def evaluate_expectations(
    prompt: dict[str, Any],
    *,
    http_status: int,
    content: str,
    lane: str,
    lane_path: str,
    finish_reason: str,
    error: str,
) -> dict[str, Any]:
    expect = prompt.get("expect") if isinstance(prompt.get("expect"), dict) else {}
    checks: list[dict[str, Any]] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    add_check("http_status", http_status == 200, f"expected=200 observed={http_status}")
    add_check("error_empty", not error, error or "ok")

    allowed_lanes = normalize_string_list(expect.get("allowed_lanes"))
    if allowed_lanes:
        add_check(
            "allowed_lanes",
            lane in allowed_lanes,
            f"allowed={allowed_lanes} observed={lane or '<missing>'}",
        )

    forbidden_lanes = normalize_string_list(expect.get("forbidden_lanes"))
    if forbidden_lanes:
        add_check(
            "forbidden_lanes",
            lane not in forbidden_lanes,
            f"forbidden={forbidden_lanes} observed={lane or '<missing>'}",
        )

    allowed_lane_paths = normalize_string_list(expect.get("allowed_lane_paths"))
    if allowed_lane_paths:
        add_check(
            "allowed_lane_paths",
            lane_path in allowed_lane_paths,
            f"allowed={allowed_lane_paths} observed={lane_path or '<missing>'}",
        )

    forbidden_lane_paths = normalize_string_list(expect.get("forbidden_lane_paths"))
    if forbidden_lane_paths:
        add_check(
            "forbidden_lane_paths",
            lane_path not in forbidden_lane_paths,
            f"forbidden={forbidden_lane_paths} observed={lane_path or '<missing>'}",
        )

    min_content_chars = as_int(expect.get("min_content_chars"))
    if min_content_chars > 0:
        add_check(
            "min_content_chars",
            len(content) >= min_content_chars,
            f"minimum={min_content_chars} observed={len(content)}",
        )

    max_content_chars = as_int(expect.get("max_content_chars"))
    if max_content_chars > 0:
        add_check(
            "max_content_chars",
            len(content) <= max_content_chars,
            f"maximum={max_content_chars} observed={len(content)}",
        )

    must_contain = compile_patterns(normalize_string_list(expect.get("must_contain_regex")))
    for idx, pattern in enumerate(must_contain, start=1):
        matched = bool(pattern.search(content))
        add_check(
            f"must_contain_regex_{idx}",
            matched,
            f"pattern={pattern.pattern!r} matched={matched}",
        )

    must_not_contain = compile_patterns(normalize_string_list(expect.get("must_not_contain_regex")))
    for idx, pattern in enumerate(must_not_contain, start=1):
        matched = bool(pattern.search(content))
        add_check(
            f"must_not_contain_regex_{idx}",
            not matched,
            f"pattern={pattern.pattern!r} matched={matched}",
        )

    expected_finish_reasons = normalize_string_list(expect.get("allowed_finish_reasons"))
    if expected_finish_reasons:
        add_check(
            "allowed_finish_reasons",
            finish_reason in expected_finish_reasons,
            f"allowed={expected_finish_reasons} observed={finish_reason or '<missing>'}",
        )

    passed = all(bool(check["passed"]) for check in checks)
    return {"passed": passed, "checks": checks}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_summary(rows: list[dict[str, Any]], *, args: argparse.Namespace) -> dict[str, Any]:
    category_totals: dict[str, dict[str, int]] = {}
    for row in rows:
        category = str(row.get("category") or "general")
        entry = category_totals.setdefault(category, {"total": 0, "passed": 0, "failed": 0})
        entry["total"] += 1
        if row.get("passed"):
            entry["passed"] += 1
        else:
            entry["failed"] += 1

    return {
        "captured_at": now_iso_utc(),
        "url": args.url,
        "model": args.model,
        "prompts_file": str(Path(args.prompts_file).expanduser().resolve()),
        "prompt_count": len(rows),
        "passed": sum(1 for row in rows if row.get("passed")),
        "failed": sum(1 for row in rows if not row.get("passed")),
        "categories": category_totals,
    }


def command_capture(args: argparse.Namespace) -> int:
    prompts = load_prompts(args.prompts_file, args.prompt_limit)
    if not prompts:
        print("No prompts loaded.", file=sys.stderr)
        return 2

    output_dir = make_output_dir(args.output_dir)
    capture_path = output_dir / "frontdoor_capture.jsonl"
    summary_path = output_dir / "frontdoor_summary.json"

    print(f"URL:         {args.url}")
    print(f"Model:       {args.model}")
    print(f"Prompts:     {len(prompts)}")
    print(f"Output dir:  {output_dir}")
    print()

    rows: list[dict[str, Any]] = []
    for idx, prompt in enumerate(prompts, start=1):
        payload = build_payload(prompt, args)
        started = now_iso_utc()
        try:
            http_status, data, elapsed, headers = post_json(args.url, payload, timeout=args.timeout)
            error = ""
        except urllib.error.HTTPError as exc:
            elapsed = 0.0
            http_status = int(exc.code)
            headers = {key.lower(): value for key, value in exc.headers.items()}
            try:
                body = exc.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                error = str(data.get("error", {}).get("message") or data.get("detail") or body[:240])
            except Exception:
                data = {}
                error = f"HTTP {exc.code}"
        except Exception as exc:
            elapsed = 0.0
            http_status = 0
            data = {}
            headers = {}
            error = str(exc)

        content = extract_openai_content(data) if isinstance(data, dict) else ""
        finish_reason = extract_finish_reason(data) if isinstance(data, dict) else ""
        lane_headers = {
            key: str(headers.get(header_name) or "").strip()
            for key, header_name in LANE_HEADER_MAP.items()
        }
        evaluation = evaluate_expectations(
            prompt,
            http_status=http_status,
            content=content,
            lane=lane_headers["lane"],
            lane_path=lane_headers["lane_path"],
            finish_reason=lane_headers["finish_reason"] or finish_reason,
            error=error,
        )

        row = {
            "captured_at": started,
            "id": prompt["id"],
            "category": prompt["category"],
            "prompt": prompt["prompt"],
            "notes": prompt.get("notes") or "",
            "http_status": http_status,
            "error": error,
            "content": content,
            "content_chars": len(content),
            "response_finish_reason": finish_reason,
            "headers": lane_headers,
            "elapsed_seconds": elapsed,
            "passed": evaluation["passed"],
            "checks": evaluation["checks"],
        }
        rows.append(row)

        status_text = "PASS" if evaluation["passed"] else "FAIL"
        lane_path_text = lane_headers["lane_path"] or "<missing>"
        print(
            f"[{idx:02d}/{len(prompts)}] {prompt['id']}: {status_text} "
            f"lane_path={lane_path_text} chars={len(content)}"
        )
        if args.sleep > 0 and idx < len(prompts):
            time.sleep(args.sleep)

    write_jsonl(capture_path, rows)
    summary = build_summary(rows, args=args)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print()
    print(f"Capture:     {capture_path}")
    print(f"Summary:     {summary_path}")
    print(f"Passed:      {summary['passed']}/{summary['prompt_count']}")
    print(f"Failed:      {summary['failed']}/{summary['prompt_count']}")

    if summary["failed"] and not args.allow_failures:
        return 1
    return 0


def main() -> int:
    args = parse_args()
    return command_capture(args)


if __name__ == "__main__":
    raise SystemExit(main())
