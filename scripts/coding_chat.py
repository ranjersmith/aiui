#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the aiui Qwen coding backend.")
    parser.add_argument("prompt", nargs="*", help="Prompt to send. Falls back to stdin when omitted.")
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:3391/v1/chat/completions",
        help="Coding agent chat-completions endpoint.",
    )
    parser.add_argument(
        "--repo-path",
        default="/workspace",
        help="Repository path as seen by the coding-agent container.",
    )
    parser.add_argument(
        "--model",
        default="Qwen3.5-9B-BF16.gguf",
        help="Model id to report in the request payload.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream assistant output as it arrives.",
    )
    parser.add_argument(
        "--agent-name",
        default="manual-cli",
        help="Agent name to report during the contract handshake.",
    )
    parser.add_argument(
        "--agent-kind",
        default="manual",
        help="Agent kind to report during the contract handshake.",
    )
    parser.add_argument(
        "--session-id",
        default="",
        help="Optional stable session id for the contract handshake.",
    )
    parser.add_argument(
        "--skip-handshake",
        action="store_true",
        help="Skip the repo contract handshake before sending the chat request.",
    )
    return parser.parse_args()


def read_prompt(args: argparse.Namespace) -> str:
    cli_prompt = " ".join(args.prompt).strip()
    if cli_prompt:
        return cli_prompt
    piped = sys.stdin.read().strip()
    if piped:
        return piped
    raise SystemExit("prompt is required (argument or stdin)")


def stream_response(req: urllib.request.Request) -> int:
    with urllib.request.urlopen(req) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload_text = line[5:].strip()
            if not payload_text or payload_text == "[DONE]":
                continue
            payload = json.loads(payload_text)
            choices = payload.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            delta = choices[0].get("delta")
            if not isinstance(delta, dict):
                continue
            text = delta.get("content")
            if isinstance(text, str) and text:
                sys.stdout.write(text)
                sys.stdout.flush()
    sys.stdout.write("\n")
    return 0


def one_shot_response(req: urllib.request.Request) -> int:
    with urllib.request.urlopen(req) as response:
        body = json.loads(response.read().decode("utf-8"))
    text = str(body["choices"][0]["message"]["content"])
    sys.stdout.write(text.strip() + "\n")
    return 0


def contract_base_url(endpoint: str) -> str:
    suffix = "/v1/chat/completions"
    if endpoint.endswith(suffix):
        return endpoint[: -len(suffix)]
    return endpoint.rstrip("/")


def perform_handshake(args: argparse.Namespace) -> dict[str, str]:
    payload = {
        "agent_name": args.agent_name,
        "agent_kind": args.agent_kind,
        "session_id": args.session_id or None,
        "repo_path": args.repo_path,
        "capabilities": ["chat"],
    }
    req = urllib.request.Request(
        contract_base_url(args.endpoint) + "/v1/agent-contract/handshake",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as response:
        body = json.loads(response.read().decode("utf-8"))
    headers = body.get("required_headers")
    if not isinstance(headers, dict) or not headers:
        raise SystemExit("agent contract handshake returned no required_headers")
    return {str(key): str(value) for key, value in headers.items() if str(value).strip()}


def main() -> int:
    args = parse_args()
    prompt = read_prompt(args)
    payload = {
        "model": args.model,
        "stream": args.stream,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "content-type": "application/json",
        "X-AIUI-Repo-Path": args.repo_path,
    }
    if not args.skip_handshake:
        headers.update(perform_handshake(args))

    req = urllib.request.Request(
        args.endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        if args.stream:
            return stream_response(req)
        return one_shot_response(req)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"HTTP {exc.code}: {detail}\n")
        return 1
    except urllib.error.URLError as exc:
        sys.stderr.write(f"Request failed: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
