#!/usr/bin/env python3
# [EXPERIMENTAL] Qwen Agent smoke test
# ⚠️  Experimental test utility for Qwen Agent debugging. Not for production.
"""Minimal Qwen-Agent smoke test against an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import re
from typing import Any

from qwen_agent.agents import Assistant


def has_malformed_math_delimiters(text: str) -> bool:
    without_code = re.sub(r"```[\s\S]*?```", "", text)
    display_count = len(re.findall(r"(?<!\\)\$\$", without_code))
    if display_count % 2 != 0:
        return True

    masked = re.sub(r"(?<!\\)\$\$[\s\S]*?(?<!\\)\$\$", "", without_code)
    inline_count = len(re.findall(r"(?<!\\)(?<!\$)\$(?!\$)", masked))
    return inline_count % 2 != 0


def extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload

    if isinstance(payload, list):
        chunks: list[str] = []
        for item in payload:
            if isinstance(item, dict) and "text" in item:
                chunks.append(str(item.get("text", "")))
            else:
                chunks.append(str(item))
        return "\n".join(chunks).strip()

    return str(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct")
    parser.add_argument("--server", default="http://127.0.0.1:8081/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument(
        "--prompt",
        default="solve quadratic equations with formulas and final roots",
    )
    args = parser.parse_args()

    llm_cfg = {
        "model": args.model,
        "model_server": args.server,
        "api_key": args.api_key,
        "generate_cfg": {
            "top_p": 0.8,
            "temperature": 0.2,
            "max_input_tokens": 12000,
        },
    }

    bot = Assistant(llm=llm_cfg, function_list=[], system_message="")
    messages = [{"role": "user", "content": args.prompt}]
    response = list(bot.run(messages=messages))[-1]
    text = extract_text(response[-1].get("content", ""))

    malformed = has_malformed_math_delimiters(text)
    print("qwen-agent result")
    print(f"model={args.model}")
    print(f"server={args.server}")
    print(f"malformed_math_delimiters={malformed}")
    print("--- output ---")
    print(text)
    print("--- end ---")

    return 0 if not malformed else 2


if __name__ == "__main__":
    raise SystemExit(main())
