#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "http://127.0.0.1:8082/v1"
DEFAULT_MODEL = "Qwen3-VL-4B-Instruct-UD-Q6_K_XL.gguf"
DEFAULT_API_KEY = "EMPTY"

TASK_PROMPTS = {
    "describe": (
        "Describe only what is visibly present in this image. "
        "Do not guess brands, films, bands, celebrities, or cultural references unless they are explicitly shown."
    ),
    "ocr": (
        "Perform OCR on this image. Extract all visible text as faithfully as possible, preserving line breaks when useful. "
        "If text is unclear, mark it as [unclear]."
    ),
    "document": (
        "Parse this document image. Return JSON with keys: title, sections, tables, key_values, visible_text_summary. "
        "Use empty strings or empty arrays when information is missing."
    ),
    "grounding": (
        "Identify the object or region requested by the user. "
        "Return a concise answer describing where it is in the image using relative positions only "
        "(for example: top-left, center-right, lower third). "
        "If the request cannot be grounded confidently, say uncertain."
    ),
    "mmcode": (
        "Analyze the image as a UI or design reference. "
        "Return a concise implementation plan covering layout, typography, colors, spacing, and interaction hints."
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe the live 8082 Qwen3-VL service with cookbook-style prompts."
    )
    parser.add_argument("image", help="Local image path or image URL")
    parser.add_argument(
        "--task",
        choices=sorted(TASK_PROMPTS),
        default="describe",
        help="Preset task prompt to use",
    )
    parser.add_argument(
        "--prompt",
        help="Optional extra user prompt appended after the task preset",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="OpenAI-compatible base URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model id to send")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="API key value")
    parser.add_argument("--max-tokens", type=int, default=512, help="Generation limit")
    parser.add_argument(
        "--temperature", type=float, default=0.1, help="Sampling temperature for the request"
    )
    parser.add_argument(
        "--system",
        default=(
            "You are a precise multimodal analyst. "
            "Prefer literal observation over interpretation, and state uncertainty plainly."
        ),
        help="System prompt override",
    )
    return parser


def image_to_url(value: str) -> str:
    if value.startswith(("http://", "https://", "data:")):
        return value
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    mime_type, _ = mimetypes.guess_type(path.name)
    if not mime_type:
        mime_type = "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_payload(args: argparse.Namespace) -> dict:
    prompt_parts = [TASK_PROMPTS[args.task]]
    if args.prompt:
        prompt_parts.append(args.prompt.strip())
    user_text = "\n\n".join(part for part in prompt_parts if part)
    return {
        "model": args.model,
        "stream": False,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "messages": [
            {"role": "system", "content": args.system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": image_to_url(args.image)}},
                ],
            },
        ],
    }


def post_json(url: str, payload: dict, api_key: str) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    url = args.base_url.rstrip("/") + "/chat/completions"
    payload = build_payload(args)
    try:
        result = post_json(url, payload, args.api_key)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1

    try:
        message = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
