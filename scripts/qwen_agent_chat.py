#!/usr/bin/env python3
"""Interactive Qwen-Agent chat against an OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
from typing import Any

from qwen_agent.agents import Assistant


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
        "--system",
        default="You are a concise math assistant. Use clean TeX delimiters for equations.",
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

    bot = Assistant(llm=llm_cfg, function_list=[], system_message=args.system)
    messages: list[dict[str, Any]] = []

    print("Qwen-Agent interactive chat")
    print("Type /exit to quit.")

    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_text:
            continue
        if user_text in {"/exit", "exit", "quit"}:
            print("Exiting.")
            break

        messages.append({"role": "user", "content": user_text})
        final = list(bot.run(messages=messages))[-1]
        assistant_msg = final[-1]
        text = extract_text(assistant_msg.get("content", ""))
        print(f"\nAgent: {text}")
        messages.append({"role": "assistant", "content": text})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
