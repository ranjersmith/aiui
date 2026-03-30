#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run repeated non-stream chat completion calls and report token speed.",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("AIUI_BENCH_URL", "http://127.0.0.1:3390/v1/chat/completions"),
        help="OpenAI-compatible /v1/chat/completions endpoint",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("AIUI_DEFAULT_MODEL", "Qwen3.5-9B-BF16.gguf"),
        help="Model id to request",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of benchmark runs",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="max_tokens for each run",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request timeout in seconds",
    )
    parser.add_argument(
        "--prompt",
        default="Summarize Newtons second law in 6 bullet points with one equation.",
        help="Prompt to benchmark",
    )
    return parser.parse_args()


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started_at = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    elapsed = max(time.perf_counter() - started_at, 1e-6)
    decoded = json.loads(raw.decode("utf-8"))
    return decoded, elapsed


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


def main() -> int:
    args = parse_args()
    if args.runs <= 0:
        print("runs must be >= 1", file=sys.stderr)
        return 2

    print(f"URL:   {args.url}")
    print(f"Model: {args.model}")
    print(f"Runs:  {args.runs}")
    print(f"Prompt: {args.prompt}")
    print()

    completion_tps_values: list[float] = []
    prompt_tps_values: list[float] = []
    wall_tps_values: list[float] = []

    for run in range(1, args.runs + 1):
        payload = {
            "model": args.model,
            "stream": False,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "messages": [{"role": "user", "content": args.prompt}],
        }

        try:
            data, elapsed = post_json(args.url, payload, timeout=args.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"run {run}: HTTP {exc.code} {detail[:240]}", file=sys.stderr)
            return 1
        except Exception as exc:  # pragma: no cover - defensive runtime path
            print(f"run {run}: request failed: {exc}", file=sys.stderr)
            return 1

        usage = data.get("usage") if isinstance(data, dict) else {}
        timings = data.get("timings") if isinstance(data, dict) else {}

        prompt_tokens = as_int(usage.get("prompt_tokens"))
        completion_tokens = as_int(usage.get("completion_tokens"))
        prompt_tps = as_float(timings.get("prompt_per_second"))
        completion_tps = as_float(timings.get("predicted_per_second"))
        wall_tps = (completion_tokens / elapsed) if completion_tokens > 0 else 0.0

        prompt_tps_values.append(prompt_tps)
        completion_tps_values.append(completion_tps)
        wall_tps_values.append(wall_tps)

        print(
            f"run {run}: ctx {prompt_tokens} | tok {completion_tokens} | "
            f"server {completion_tps:.2f} tok/s | wall {wall_tps:.2f} tok/s | "
            f"prompt {prompt_tps:.2f} tok/s"
        )

    avg_completion_tps = statistics.fmean(completion_tps_values)
    avg_wall_tps = statistics.fmean(wall_tps_values)
    avg_prompt_tps = statistics.fmean(prompt_tps_values)

    print()
    print("summary:")
    print(f"  avg completion tok/s (server): {avg_completion_tps:.2f}")
    print(f"  avg completion tok/s (wall):   {avg_wall_tps:.2f}")
    print(f"  avg prompt tok/s:              {avg_prompt_tps:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
