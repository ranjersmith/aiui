from __future__ import annotations

import asyncio
import ast
import base64
import binascii
import copy
import io
import json
import math
import mimetypes
import operator
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent


def env_bool(key: str, default: bool = False) -> bool:
    """Parse env var as boolean: '1', 'true', 'yes' → True, everything else → False."""
    return os.getenv(key, "").strip().lower() in {"1", "true", "yes"}


def env_int(key: str, default: int) -> int:
    """Parse env var as int with fallback."""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def env_float(key: str, default: float) -> float:
    """Parse env var as float with fallback."""
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


LLM_BASE_URL = os.getenv("AIUI_LLM_BASE_URL", "http://host.docker.internal:8081").rstrip("/")
FAST_LLM_BASE_URL = os.getenv("AIUI_FAST_LLM_BASE_URL", "http://host.docker.internal:8082").rstrip("/")
DEFAULT_MODEL = os.getenv("AIUI_DEFAULT_MODEL", "Qwen3-Coder-30B-A3B-Instruct-UD-Q6_K_XL.gguf")
REQUEST_TIMEOUT_SECONDS = int(os.getenv("AIUI_REQUEST_TIMEOUT_SECONDS", "120"))
SYSTEM_PROMPT = os.getenv("AIUI_SYSTEM_PROMPT", "You are a concise, helpful assistant.").strip()
# CANONICAL MATH DELIMITER CONTRACT: See MATH_DELIMITERS_CONTRACT.json for the contract.
# Backend guidance: Use \(...\) for inline math, $$...$$ for display math.
RESPONSE_FORMAT_GUIDANCE = (
    "Response format requirements:\n"
    "- Return valid Markdown.\n"
    "- Use \\(...\\) for inline math (canonical delimiter). Never use single $.\n"
    "- Use $$...$$ for display math.\n"
    "- Every math delimiter must be balanced and closed.\n"
    "- Before finishing, verify there are no unmatched $, $$, \\(, or \\).\n"
    "- Do not place LaTeX outside math delimiters.\n"
    "- Do not wrap equations in bold or italics.\n"
    "- Leave a blank line before and after headings, lists, and display equations.\n"
    "- Keep headings complete (for example, '## Heading').\n"
    "- Keep lists valid and consistently indented.\n"
    "- Do not emit truncated or unfinished sentences.\n"
    "- Close all formatting markers: **, _, and code fences."
)
DEFAULT_API_KEY = os.getenv("AIUI_OPENAI_API_KEY", "").strip()
UPSTREAM_HEALTH_TIMEOUT_SECONDS = env_float("AIUI_UPSTREAM_HEALTH_TIMEOUT_SECONDS", 8.0)
CONTEXT_BUDGET_TOKENS = env_int("AIUI_CONTEXT_BUDGET_TOKENS", 4096)
CONTEXT_REPLY_RESERVE_TOKENS = env_int("AIUI_CONTEXT_REPLY_RESERVE_TOKENS", 1024)
MODULE_CATALOG_CACHE_TTL_SECONDS = env_float("AIUI_MODULE_CATALOG_CACHE_TTL_SECONDS", 60.0)
AGENT_MAX_LLM_CALLS_PER_RUN = env_int("AIUI_AGENT_MAX_LLM_CALLS_PER_RUN", 6)
AGENT_MAX_TOOL_CALLS_PER_TURN = env_int("AIUI_AGENT_MAX_TOOL_CALLS_PER_TURN", 4)
AGENT_ENABLE_NON_STREAM_LOOP = env_bool("AIUI_AGENT_ENABLE_NON_STREAM_LOOP", True)
AGENT_ENABLE_STREAM_LOOP = env_bool("AIUI_AGENT_ENABLE_STREAM_LOOP", True)
# SECURITY: Disable doc/ppt external extractors by default to avoid unexpected process spawning.
# Set AIUI_ENABLE_EXTERNAL_EXTRACTORS=1 to enable catppt, catdoc, antiword extraction.
ENABLE_EXTERNAL_EXTRACTORS = env_bool("AIUI_ENABLE_EXTERNAL_EXTRACTORS", False)
MAX_ATTACHMENTS = env_int("AIUI_MAX_ATTACHMENTS", env_int("AIUI_MAX_IMAGE_ATTACHMENTS", 4))
MAX_ATTACHMENT_DATA_URL_CHARS = env_int(
    "AIUI_MAX_ATTACHMENT_DATA_URL_CHARS", env_int("AIUI_MAX_IMAGE_DATA_URL_CHARS", 8000000)
)
MAX_DOCUMENT_BYTES = env_int("AIUI_MAX_DOCUMENT_BYTES", 12000000)
MAX_DOCUMENT_TEXT_CHARS = env_int("AIUI_MAX_DOCUMENT_TEXT_CHARS", 16000)
MAX_TOTAL_DOCUMENT_TEXT_CHARS = env_int("AIUI_MAX_TOTAL_DOCUMENT_TEXT_CHARS", 48000)
IMAGE_PART_TOKEN_ESTIMATE = env_int("AIUI_IMAGE_PART_TOKEN_ESTIMATE", 768)
PARKER_EVIDENCE_LABEL_RE = re.compile(r"\[E\d+\]")
PARKER_EVIDENCE_BULLET_RE = re.compile(r"(?mi)^\s*-\s*\[E\d+\]\s+")
TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.IGNORECASE | re.DOTALL)
_MODULE_CATALOG_CACHE: dict[str, Any] = {"expires_at": 0.0, "body": None}
TEXT_DOCUMENT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".py",
    ".log",
}
WORDPROCESSINGML_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DRAWINGML_TEXT_TAG = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"


def build_agent_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": "get_current_time",
            "description": "Get the current date and time. Optionally provide a timezone like UTC, America/New_York, Europe/London, or Asia/Tokyo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone name, e.g., UTC or America/New_York",
                    }
                },
                "required": [],
            },
        },
        {
            "name": "calculator",
            "description": "Evaluate a safe arithmetic expression using +, -, *, /, //, %, and **.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Arithmetic expression such as (12 + 5) * 3 / 2",
                    }
                },
                "required": ["expression"],
            },
        },
        {
            "name": "search_conversation",
            "description": "Search prior conversation turns and return the most relevant snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search in prior conversation turns",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of snippets to return",
                    },
                },
                "required": ["query"],
            },
        },
    ]


def build_nous_tools_instruction(tool_specs: list[dict[str, Any]]) -> str:
    tool_descs = "\n".join(
        json.dumps({"type": "function", "function": spec}, ensure_ascii=False) for spec in tool_specs
    )
    return (
        "# Tools\n\n"
        "You may call one or more functions to assist with the user query.\n\n"
        "You are provided with function signatures within <tools></tools> XML tags:\n"
        "<tools>\n"
        f"{tool_descs}\n"
        "</tools>\n\n"
        "For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:\n"
        "<tool_call>\n"
        '{"name": <function-name>, "arguments": <args-json-object>}\n'
        "</tool_call>"
    )


def inject_tools_into_messages(messages: list[dict[str, Any]], tool_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not tool_specs:
        return messages

    out = copy.deepcopy(messages)
    tool_instruction = build_nous_tools_instruction(tool_specs)

    if out and out[0].get("role") == "system":
        current = str(out[0].get("content") or "")
        if "<tools>" not in current:
            out[0]["content"] = f"{current}\n\n{tool_instruction}".strip()
    else:
        out.insert(0, {"role": "system", "content": tool_instruction})
    return out


def _parse_tool_call_payload(raw_payload: str) -> tuple[str, dict[str, Any]] | None:
    payload = str(raw_payload or "").strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    name = str(parsed.get("name") or "").strip()
    if not name:
        return None
    arguments = parsed.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {}
    return name, arguments


def parse_assistant_tool_calls(text: str) -> tuple[list[tuple[str, dict[str, Any]]], str]:
    if not text:
        return [], ""

    calls: list[tuple[str, dict[str, Any]]] = []
    for match in TOOL_CALL_BLOCK_RE.finditer(text):
        parsed = _parse_tool_call_payload(match.group(1))
        if parsed is not None:
            calls.append(parsed)

    visible_text = TOOL_CALL_BLOCK_RE.sub("", text).strip()
    return calls, visible_text


def parse_stream_delta_for_tool_events(
    buffer: str,
) -> tuple[list[str], list[dict[str, Any]], str]:
    """Extract complete <tool_call> blocks from a streaming buffer.

    Returns:
      visible_chunks: text segments safe to render to user.
      tool_events: parsed tool call events.
      remainder: partial tail to keep buffering.
    """
    visible_chunks: list[str] = []
    tool_events: list[dict[str, Any]] = []
    working = str(buffer or "")

    while True:
        match = TOOL_CALL_BLOCK_RE.search(working)
        if not match:
            # Keep a small tail in case a <tool_call> tag is split across chunks.
            keep_tail = len("<tool_call>") - 1
            if len(working) > keep_tail:
                visible_chunks.append(working[:-keep_tail])
                working = working[-keep_tail:]
            return visible_chunks, tool_events, working

        before = working[: match.start()]
        if before:
            visible_chunks.append(before)

        parsed = _parse_tool_call_payload(match.group(1))
        if parsed is not None:
            tool_name, tool_args = parsed
            tool_events.append({"type": "tool_call", "name": tool_name, "arguments": tool_args})

        working = working[match.end() :]


def safe_eval_arithmetic(expression: str) -> float:
    allowed_ops: dict[type, Any] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_ops:
            return float(allowed_ops[type(node.op)](_eval(node.operand)))
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
            left = _eval(node.left)
            right = _eval(node.right)
            return float(allowed_ops[type(node.op)](left, right))
        raise ValueError("Expression contains unsupported syntax")

    tree = ast.parse(expression, mode="eval")
    return _eval(tree)


def execute_agent_tool(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    if tool_name == "get_current_time":
        timezone_name = str(tool_args.get("timezone") or "UTC").strip() or "UTC"
        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            timezone_name = "UTC"
            tz = timezone.utc
        now = datetime.now(tz)
        return {
            "timezone": timezone_name,
            "iso": now.isoformat(),
            "readable": now.strftime("%A, %d %B %Y, %H:%M:%S %Z"),
        }

    if tool_name == "calculator":
        expression = str(tool_args.get("expression") or "").strip()
        if not expression:
            return {"error": "expression is required"}
        try:
            value = safe_eval_arithmetic(expression)
            return {"expression": expression, "result": value}
        except Exception as exc:
            return {"expression": expression, "error": str(exc)}

    if tool_name == "search_conversation":
        query = str(tool_args.get("query") or "").strip().lower()
        if not query:
            return {"error": "query is required"}

        max_results = max(1, min(10, as_int(tool_args.get("max_results") or 3)))
        scored: list[tuple[int, dict[str, Any]]] = []
        query_terms = [term for term in re.split(r"\s+", query) if term]
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            text = extract_summary_text(msg.get("content"))
            normalized = text.lower()
            if not normalized:
                continue
            score = sum(1 for term in query_terms if term in normalized)
            if score <= 0:
                continue
            scored.append(
                (
                    score,
                    {
                        "role": str(msg.get("role") or ""),
                        "snippet": compact_text(text, 280),
                    },
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return {
            "query": query,
            "matches": [item[1] for item in scored[:max_results]],
            "count": len(scored),
        }

    return {"error": f"unknown tool: {tool_name}"}


def make_tool_response_message(tool_result: dict[str, Any]) -> dict[str, str]:
    return {
        "role": "user",
        "content": "<tool_response>\n"
        + json.dumps(tool_result, ensure_ascii=False)
        + "\n</tool_response>",
    }


async def run_agent_non_stream(
    *,
    messages: list[dict[str, Any]],
    model: str,
    mode: str | None,
    temperature: float,
    max_tokens: int | None,
) -> str:
    tool_specs = build_agent_tool_specs()
    working_messages = inject_tools_into_messages(messages, tool_specs)

    last_visible_text = ""
    for _ in range(max(1, AGENT_MAX_LLM_CALLS_PER_RUN)):
        assistant_text = await call_llm_chat(
            messages=working_messages,
            model=model,
            mode=mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        tool_calls, visible_text = parse_assistant_tool_calls(assistant_text)
        if visible_text:
            last_visible_text = visible_text

        if not tool_calls:
            return visible_text or assistant_text

        working_messages.append({"role": "assistant", "content": assistant_text})

        calls_to_execute = tool_calls[: max(1, AGENT_MAX_TOOL_CALLS_PER_TURN)]
        for tool_name, tool_args in calls_to_execute:
            tool_result = execute_agent_tool(
                tool_name=tool_name,
                tool_args=tool_args,
                messages=working_messages,
            )
            wrapped_result = {
                "tool": tool_name,
                "arguments": tool_args,
                "result": tool_result,
            }
            working_messages.append(make_tool_response_message(wrapped_result))

    if last_visible_text:
        return last_visible_text
    return "I could not finish tool planning within the safety limit."


class Attachment(BaseModel):
    type: Literal["image", "document"] = "image"
    data_url: str = Field(default="", max_length=10000000)
    name: str = Field(default="", max_length=260)
    mime_type: str = Field(default="", max_length=200)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    attachments: list[Attachment] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    context_summary: str | None = Field(default=None, max_length=4000)
    context_budget_tokens: int | None = Field(default=None, ge=0, le=128000)
    model: str | None = None
    mode: str | None = Field(default=None, max_length=64)
    context_mode: Literal["trim", "summarize"] | None = None
    stream: bool = True
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


_CODING_MODES = frozenset({"code", "coding", "coder", "dev", "develop", "agent"})


def resolve_llm_base_url(mode: str | None) -> str:
    """Route coding/agent modes to the heavy coder LLM (8081), everything else to the fast LLM (8082)."""
    if mode and mode.strip().lower() in _CODING_MODES:
        return LLM_BASE_URL
    return FAST_LLM_BASE_URL


def build_upstream_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if DEFAULT_API_KEY:
        headers["Authorization"] = f"Bearer {DEFAULT_API_KEY}"
    return headers


def build_http_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=10.0,
        read=float(REQUEST_TIMEOUT_SECONDS),
        write=30.0,
        pool=10.0,
    )


def build_health_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=min(UPSTREAM_HEALTH_TIMEOUT_SECONDS, 5.0),
        read=UPSTREAM_HEALTH_TIMEOUT_SECONDS,
        write=5.0,
        pool=5.0,
    )


# Rate limiting and attachment abuse guardrails
_REQUEST_TIMESTAMPS: list[float] = []  # Track per-second request rate
_MAX_REQUESTS_PER_SECOND = int(os.getenv("AIUI_MAX_REQUESTS_PER_SECOND", "10"))
_MAX_ATTACHMENT_BYTES_PER_REQUEST = int(os.getenv("AIUI_MAX_ATTACHMENT_BYTES_PER_REQUEST", "25000000"))


def check_rate_limit() -> None:
    """Enforce per-second rate limit to prevent abuse."""
    now = time.perf_counter()
    _REQUEST_TIMESTAMPS[:] = [t for t in _REQUEST_TIMESTAMPS if now - t < 1.0]
    if len(_REQUEST_TIMESTAMPS) >= _MAX_REQUESTS_PER_SECOND:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _REQUEST_TIMESTAMPS.append(now)


def validate_attachments(attachments: list[Attachment]) -> None:
    """Enforce attachment size and count guardrails to prevent abuse."""
    if len(attachments) > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=413,
            detail=f"Too many attachments (max {MAX_ATTACHMENTS}), got {len(attachments)}",
        )
    total_bytes = 0
    for a in attachments:
        if a.data:
            try:
                total_bytes += len(base64.b64decode(a.data))
            except (binascii.Error, ValueError):
                pass  # Invalid base64; will be caught elsewhere
    if total_bytes > _MAX_ATTACHMENT_BYTES_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment payload too large (max {_MAX_ATTACHMENT_BYTES_PER_REQUEST} bytes), got {total_bytes}",
        )


def format_httpx_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return f"{exc.__class__.__name__}: upstream timed out after {REQUEST_TIMEOUT_SECONDS}s"

    if isinstance(exc, httpx.ConnectError):
        return f"{exc.__class__.__name__}: could not connect to upstream"

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = ""
        try:
            data = exc.response.json()
            if isinstance(data, dict):
                detail = str(data.get("detail") or data.get("error") or "").strip()
        except Exception:
            detail = ""
        if not detail:
            detail = (exc.response.text or "").strip()[:220]
        if detail:
            return f"HTTP {status}: {detail}"
        return f"HTTP {status}"

    base = str(exc).strip()
    if base:
        return f"{exc.__class__.__name__}: {base}"
    return exc.__class__.__name__


def build_fallback_module_catalog(*, upstream_error: str | None = None) -> dict[str, Any]:
    return {
        "service": "ui",
        "version": "v1",
        "default_mode": "chat",
        "core_mode": "chat",
        "source": "fallback",
        "upstream_error": upstream_error,
        "modes": [
            {
                "id": "chat",
                "route": "chat",
                "label": "Chat",
                "description": (
                    "Standalone core chat. Add-ins appear only when the upstream orchestrator exposes them."
                ),
                "primary_lane": "chat",
                "kind": "core",
                "selection": "default",
                "user_selectable": True,
            }
        ],
    }


async def load_module_catalog() -> dict[str, Any]:
    cached_body = _MODULE_CATALOG_CACHE.get("body")
    cached_expires_at = float(_MODULE_CATALOG_CACHE.get("expires_at") or 0.0)
    if isinstance(cached_body, dict) and time.monotonic() < cached_expires_at:
        return dict(cached_body)

    try:
        async with httpx.AsyncClient(timeout=build_health_timeout()) as client:
            response = await client.get(
                f"{LLM_BASE_URL}/v1/modules",
                headers=build_upstream_headers(),
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        result = build_fallback_module_catalog(upstream_error=format_httpx_error(exc))
        _MODULE_CATALOG_CACHE["body"] = result
        _MODULE_CATALOG_CACHE["expires_at"] = time.monotonic() + max(0.0, MODULE_CATALOG_CACHE_TTL_SECONDS)
        return dict(result)

    if not isinstance(body, dict) or not isinstance(body.get("modes"), list):
        result = build_fallback_module_catalog(upstream_error="upstream module catalog malformed")
        _MODULE_CATALOG_CACHE["body"] = result
        _MODULE_CATALOG_CACHE["expires_at"] = time.monotonic() + max(0.0, MODULE_CATALOG_CACHE_TTL_SECONDS)
        return dict(result)

    result = dict(body)
    result.setdefault("source", "upstream")
    result.setdefault("default_mode", "chat")
    result.setdefault("core_mode", str(result.get("default_mode") or "chat"))
    _MODULE_CATALOG_CACHE["body"] = result
    _MODULE_CATALOG_CACHE["expires_at"] = time.monotonic() + max(0.0, MODULE_CATALOG_CACHE_TTL_SECONDS)
    return dict(result)


def attachment_name(item: Attachment, *, fallback: str = "attachment") -> str:
    candidate = Path(str(item.name or "").strip()).name
    return candidate or fallback


def decode_attachment_data_url(data_url: str) -> tuple[str, bytes]:
    prefix, sep, payload = str(data_url or "").partition(",")
    if sep != "," or not prefix.lower().startswith("data:"):
        raise ValueError("attachment is not a valid data URL")

    metadata = prefix[5:]
    mime_type = "application/octet-stream"
    is_base64 = False
    if metadata:
        parts = [part.strip() for part in metadata.split(";") if part.strip()]
        if parts and "=" not in parts[0]:
            mime_type = parts[0].lower()
            parts = parts[1:]
        is_base64 = any(part.lower() == "base64" for part in parts)

    try:
        raw_bytes = (
            base64.b64decode(payload, validate=False) if is_base64 else urllib.parse.unquote_to_bytes(payload)
        )
    except (binascii.Error, ValueError) as exc:
        raise ValueError("attachment data URL could not be decoded") from exc

    return mime_type, raw_bytes


def normalize_image_attachments(attachments: list[Attachment]) -> list[str]:
    out: list[str] = []
    for item in attachments:
        if len(out) >= max(1, MAX_ATTACHMENTS):
            break
        if item.type != "image":
            continue
        data_url = (item.data_url or "").strip()
        if not data_url:
            continue
        if len(data_url) > max(1024, MAX_ATTACHMENT_DATA_URL_CHARS):
            continue
        if not data_url.lower().startswith("data:image/"):
            continue
        out.append(data_url)
    return out


def normalize_document_text(text: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(text or "").splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max(1, max_chars - 1)].rstrip()}…"


def decode_text_document(raw_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "utf-16le", "utf-16be", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def extract_docx_text(raw_bytes: bytes) -> str:
    paragraphs: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        document_xml = archive.read("word/document.xml")
    root = ET.fromstring(document_xml)
    for paragraph in root.findall(".//w:p", WORDPROCESSINGML_NAMESPACE):
        runs = [node.text for node in paragraph.findall(".//w:t", WORDPROCESSINGML_NAMESPACE) if node.text]
        if runs:
            paragraphs.append("".join(runs))
    return "\n".join(paragraphs)


def extract_pptx_text(raw_bytes: bytes) -> str:
    slides_out: list[str] = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for index, slide_name in enumerate(slide_names, start=1):
            root = ET.fromstring(archive.read(slide_name))
            texts = [node.text for node in root.iter(DRAWINGML_TEXT_TAG) if node.text]
            if texts:
                slides_out.append(f"Slide {index}: {' '.join(texts)}")
    return "\n\n".join(slides_out)


def extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""

    reader = PdfReader(io.BytesIO(raw_bytes))
    pages: list[str] = []
    for page in reader.pages:
        extracted = str(page.extract_text() or "").strip()
        if extracted:
            pages.append(extracted)
    return "\n\n".join(pages)


def run_external_document_extractor(
    commands: list[list[str]],
    *,
    raw_bytes: bytes,
    suffix: str,
) -> str:
    for command in commands:
        executable = shutil.which(command[0])
        if not executable:
            continue
        with tempfile.NamedTemporaryFile(suffix=suffix) as temp_file:
            temp_file.write(raw_bytes)
            temp_file.flush()
            try:
                result = subprocess.run(
                    [executable, *command[1:], temp_file.name],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
        extracted = str(result.stdout or "").strip()
        if extracted:
            return extracted
    return ""


def extract_document_text(item: Attachment) -> str:
    data_url = str(item.data_url or "").strip()
    if not data_url:
        return ""
    if len(data_url) > max(1024, MAX_ATTACHMENT_DATA_URL_CHARS):
        return ""

    try:
        parsed_mime_type, raw_bytes = decode_attachment_data_url(data_url)
    except ValueError:
        return ""

    if len(raw_bytes) > max(1, MAX_DOCUMENT_BYTES):
        return ""

    mime_type = (item.mime_type or parsed_mime_type or "").strip().lower()
    name = attachment_name(item, fallback="document")
    suffix = Path(name).suffix.lower()
    guessed_mime_type, _encoding = mimetypes.guess_type(name)
    if not mime_type and guessed_mime_type:
        mime_type = guessed_mime_type.lower()

    try:
        if mime_type.startswith("text/") or suffix in TEXT_DOCUMENT_EXTENSIONS:
            return decode_text_document(raw_bytes)
        if mime_type == "application/pdf" or suffix == ".pdf":
            return extract_pdf_text(raw_bytes)
        if (
            mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or suffix == ".docx"
        ):
            return extract_docx_text(raw_bytes)
        if mime_type in {"application/vnd.ms-powerpoint", "application/mspowerpoint"} or suffix == ".ppt":
            if not ENABLE_EXTERNAL_EXTRACTORS:
                return ""  # External extractors disabled by default; set AIUI_ENABLE_EXTERNAL_EXTRACTORS=1
            return run_external_document_extractor([["catppt"]], raw_bytes=raw_bytes, suffix=".ppt")
        if suffix == ".doc" or mime_type == "application/msword":
            if not ENABLE_EXTERNAL_EXTRACTORS:
                return ""  # External extractors disabled by default; set AIUI_ENABLE_EXTERNAL_EXTRACTORS=1
            return run_external_document_extractor(
                [["catdoc"], ["antiword"]],
                raw_bytes=raw_bytes,
                suffix=".doc",
            )
        if (
            mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            or suffix == ".pptx"
        ):
            return extract_pptx_text(raw_bytes)
    except Exception:
        return ""

    return decode_text_document(raw_bytes) if suffix in TEXT_DOCUMENT_EXTENSIONS else ""


def build_document_context(attachments: list[Attachment]) -> str:
    blocks: list[str] = []
    remaining_chars = max(0, MAX_TOTAL_DOCUMENT_TEXT_CHARS)
    for item in attachments:
        if item.type != "document":
            continue
        if remaining_chars <= 0:
            break

        name = attachment_name(item, fallback="document")
        extracted = extract_document_text(item)
        guidance = "PDF, DOCX, PPTX, TXT, Markdown, CSV, and JSON work best."
        if extracted:
            normalized = normalize_document_text(
                extracted,
                max_chars=min(MAX_DOCUMENT_TEXT_CHARS, remaining_chars),
            )
            if normalized:
                blocks.append(f"[Attached document: {name}]\n{normalized}")
                remaining_chars -= len(normalized)
                continue

        blocks.append(
            f"[Attached document: {name}]\n"
            f"(The file was attached, but its text could not be extracted here. {guidance})"
        )
        remaining_chars -= min(remaining_chars, 240)

    if not blocks:
        return ""
    return "Attached documents:\n\n" + "\n\n".join(blocks)


def build_user_text(text: str, attachments: list[Attachment]) -> str:
    clean_text = str(text or "").strip()
    document_context = build_document_context(attachments)
    if not document_context:
        return clean_text
    if not clean_text:
        return document_context
    return f"{clean_text}\n\n{document_context}".strip()


def normalize_mode_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def normalize_context_mode(value: Any) -> Literal["trim", "summarize"]:
    return "summarize" if str(value or "").strip().lower() == "summarize" else "trim"


def module_mode_ids(catalog: dict[str, Any]) -> set[str]:
    modes = catalog.get("modes")
    if not isinstance(modes, list):
        return set()
    out: set[str] = set()
    for item in modes:
        if not isinstance(item, dict):
            continue
        mode_id = normalize_mode_id(item.get("id"))
        if mode_id:
            out.add(mode_id)
    return out


def resolve_request_mode(requested_mode: Any, catalog: dict[str, Any]) -> tuple[str, str | None]:
    mode_ids = module_mode_ids(catalog)
    default_mode = normalize_mode_id(catalog.get("core_mode")) or normalize_mode_id(catalog.get("default_mode")) or "chat"
    normalized_requested_mode = normalize_mode_id(requested_mode)
    resolved_mode = normalized_requested_mode if normalized_requested_mode in mode_ids else default_mode

    if str(catalog.get("source") or "").strip().lower() != "upstream":
        return resolved_mode, None
    return resolved_mode, resolved_mode


def build_user_content(text: str, image_data_urls: list[str]) -> str | list[dict[str, Any]]:
    clean_text = (text or "").strip()
    if not image_data_urls:
        return clean_text

    content_parts: list[dict[str, Any]] = []
    if clean_text:
        content_parts.append({"type": "text", "text": clean_text})
    for data_url in image_data_urls:
        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
    return content_parts


def looks_like_library_evidence_text(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False

    lowered = cleaned.lower()
    if PARKER_EVIDENCE_BULLET_RE.search(cleaned):
        return True

    has_citation_label = bool(PARKER_EVIDENCE_LABEL_RE.search(cleaned))
    if not has_citation_label:
        return False

    return "evidence:" in lowered or "retrieved evidence" in lowered


def sanitize_context_summary(summary: str, *, mode: str) -> str:
    cleaned = str(summary or "").strip()
    if not cleaned or mode == "library":
        return cleaned

    lines = cleaned.splitlines()
    if not lines:
        return ""

    header_lines: list[str] = []
    body_lines: list[str] = []
    seen_body = False
    for line in lines:
        stripped = line.strip()
        if not seen_body and stripped and not stripped.startswith("- "):
            header_lines.append(line)
            continue

        seen_body = True
        if looks_like_library_evidence_text(line):
            continue
        body_lines.append(line)

    if not body_lines:
        return ""
    return "\n".join([*header_lines, *body_lines]).strip()


def combine_context_summaries(*summaries: str) -> str:
    parts = [str(summary or "").strip() for summary in summaries if str(summary or "").strip()]
    return "\n\n".join(parts)


def build_summary_system_prompt(system_prompt: str, context_summary: str) -> str:
    cleaned_system_prompt = str(system_prompt or "").strip()
    cleaned_context_summary = str(context_summary or "").strip()

    # Inject current date/time so the model always knows when it is.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    date_line = f"Today's date and time (UTC): {now.strftime('%A, %d %B %Y, %H:%M')} UTC."
    if cleaned_system_prompt:
        cleaned_system_prompt = f"{cleaned_system_prompt}\n{date_line}"
    else:
        cleaned_system_prompt = date_line

    cleaned_system_prompt = f"{cleaned_system_prompt}\n\n{RESPONSE_FORMAT_GUIDANCE}".strip()

    if not cleaned_context_summary:
        return cleaned_system_prompt
    summary_block = f"Older conversation summary:\n{cleaned_context_summary}"
    return f"{cleaned_system_prompt}\n\n{summary_block}"


def normalize_history(history: list[HistoryMessage], *, mode: str = "chat") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in history:
        text = build_user_text(item.content, item.attachments)
        if item.role == "assistant":
            if not text:
                continue
            if mode != "library" and looks_like_library_evidence_text(text):
                continue
            out.append({"role": "assistant", "content": text})
            continue

        if item.role == "user":
            image_data_urls = normalize_image_attachments(item.attachments)
            if not text and not image_data_urls:
                continue
            out.append({"role": "user", "content": build_user_content(text, image_data_urls)})
    return out


def compact_text(text: Any, max_len: int) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return ""
    if len(normalized) <= max_len:
        return normalized
    return f"{normalized[: max(1, max_len - 1)]}…"


def estimate_text_tokens(text: str) -> int:
    clean = str(text or "").strip()
    if not clean:
        return 0
    # Lightweight estimate: roughly 1 token per ~4 characters.
    return max(1, math.ceil(len(clean) / 4))


def estimate_content_tokens(content: Any) -> int:
    if isinstance(content, str):
        return estimate_text_tokens(content)

    if isinstance(content, list):
        total = 0
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "")
            if part_type == "text":
                total += estimate_text_tokens(str(part.get("text") or ""))
            elif part_type == "image_url":
                total += max(1, IMAGE_PART_TOKEN_ESTIMATE)
        return total

    if isinstance(content, dict):
        maybe_text = content.get("text")
        if isinstance(maybe_text, str):
            return estimate_text_tokens(maybe_text)

    # Ensure we always return an integer, default to 0 if conversion fails
    try:
        return estimate_text_tokens(str(content or ""))
    except (TypeError, ValueError):
        return 0


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        total += estimate_content_tokens(message.get("content", ""))
    return total


def extract_summary_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "").strip()
            if part_type == "text":
                text_part = str(part.get("text") or "").strip()
                if text_part:
                    parts.append(text_part)
        return " ".join(parts).strip()
    if isinstance(content, dict):
        text_value = content.get("text")
        if isinstance(text_value, str):
            return text_value
    return str(content or "").strip()


def count_summary_images(content: Any) -> int:
    if isinstance(content, list):
        total = 0
        for part in content:
            if not isinstance(part, dict):
                continue
            if str(part.get("type") or "").strip() == "image_url":
                total += 1
        return total
    return 0


def build_context_summary(
    messages: list[dict[str, Any]],
    *,
    max_items: int = 8,
    max_chars_per_item: int = 180,
    max_total_chars: int = 1800,
) -> str:
    if not messages:
        return ""

    lines: list[str] = []
    for message in messages[-max(1, int(max_items)) :]:
        if not isinstance(message, dict):
            continue
        role = "assistant" if str(message.get("role") or "").strip() == "assistant" else "user"
        snippet = compact_text(extract_summary_text(message.get("content")), max(40, int(max_chars_per_item)))
        image_count = count_summary_images(message.get("content"))
        if not snippet and image_count <= 0:
            continue
        suffix = f" [{image_count} image{'s' if image_count != 1 else ''}]" if image_count > 0 else ""
        lines.append(f"- {role}: {snippet or '(image attachment)'}{suffix}")

    if not lines:
        return ""

    summary = f"Older conversation summary (latest trimmed turns):\n{chr(10).join(lines)}"
    if len(summary) > max(200, int(max_total_chars)):
        summary = f"{summary[: max(1, int(max_total_chars) - 1)]}…"
    return summary


def safe_add_ints(a: Any, b: Any) -> int:
    """Safely add two values, converting to int if needed."""
    try:
        # Ensure we convert to integers with explicit handling
        int_a = int(a) if a is not None else 0
        int_b = int(b) if b is not None else 0
        return int_a + int_b
    except (TypeError, ValueError):
        # Fallback in case of any other error
        return 0


def select_context_budget_indices(
    messages: list[dict[str, Any]],
    budget_tokens: int,
    reserve_tokens: int = 0,
) -> list[int]:
    if budget_tokens <= 0 or not messages:
        return list(range(len(messages)))

    budget_tokens = int(budget_tokens) if budget_tokens is not None else 0
    reserve_tokens = int(reserve_tokens) if reserve_tokens is not None else 0
    usable_budget = budget_tokens - max(0, reserve_tokens)
    usable_budget = max(128, usable_budget)

    selected_indices: set[int] = set()
    last_index = len(messages) - 1
    last_message_tokens = estimate_content_tokens(messages[last_index].get("content", ""))
    selected_indices.add(last_index)
    used_tokens = last_message_tokens

    for idx in range(last_index - 1, -1, -1):
        role = messages[idx].get("role")
        if role == "system":
            continue
        token_cost = estimate_content_tokens(messages[idx].get("content", ""))
        if token_cost <= 0:
            continue
        if used_tokens + token_cost > usable_budget:
            continue
        selected_indices.add(idx)
        used_tokens += token_cost

    system_indices = [idx for idx, msg in enumerate(messages) if msg.get("role") == "system"]
    if system_indices:
        first_system = system_indices[0]
        system_token_cost = estimate_content_tokens(messages[first_system].get("content", ""))
        if used_tokens + system_token_cost <= usable_budget:
            selected_indices.add(first_system)

    return sorted(selected_indices)


def split_messages_by_context_budget(
    messages: list[dict[str, Any]],
    budget_tokens: int,
    reserve_tokens: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_indices = set(
        select_context_budget_indices(
            messages,
            budget_tokens=budget_tokens,
            reserve_tokens=reserve_tokens,
        )
    )
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for idx, message in enumerate(messages):
        if idx in selected_indices:
            kept.append(message)
        else:
            dropped.append(message)
    return kept, dropped


def apply_context_budget(
    messages: list[dict[str, Any]],
    budget_tokens: int,
    reserve_tokens: int = 0,
) -> list[dict[str, Any]]:
    if budget_tokens <= 0 or not messages:
        return messages
    kept, _dropped = split_messages_by_context_budget(
        messages,
        budget_tokens=budget_tokens,
        reserve_tokens=reserve_tokens,
    )
    return kept


def as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        # Convert to string first to handle cases where it's not directly convertible
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return 0


def build_payload_messages(req: ChatRequest, *, mode: str) -> list[dict[str, Any]]:
    text = build_user_text(req.message, req.attachments)
    request_images = normalize_image_attachments(req.attachments)
    history_messages = normalize_history(req.history, mode=mode)
    current_user_message = {"role": "user", "content": build_user_content(text, request_images)}
    conversation_messages = [*history_messages, current_user_message]
    context_budget_tokens = (
        CONTEXT_BUDGET_TOKENS if req.context_budget_tokens is None else int(req.context_budget_tokens or 0)
    )
    reserve_tokens = req.max_tokens if req.max_tokens is not None else CONTEXT_REPLY_RESERVE_TOKENS
    provided_context_summary = sanitize_context_summary((req.context_summary or "").strip(), mode=mode)
    auto_context_summary = ""

    if context_budget_tokens > 0 and normalize_context_mode(req.context_mode) == "summarize":
        kept_conversation_messages, dropped_conversation_messages = split_messages_by_context_budget(
            conversation_messages,
            budget_tokens=context_budget_tokens,
            reserve_tokens=reserve_tokens,
        )
        conversation_messages = kept_conversation_messages
        auto_context_summary = build_context_summary(dropped_conversation_messages)

    merged_system_prompt = build_summary_system_prompt(
        SYSTEM_PROMPT,
        combine_context_summaries(provided_context_summary, auto_context_summary),
    )

    payload_messages: list[dict[str, Any]] = []
    if merged_system_prompt:
        payload_messages.append({"role": "system", "content": merged_system_prompt})
    payload_messages.extend(conversation_messages)

    if context_budget_tokens > 0:
        payload_messages = apply_context_budget(
            messages=payload_messages,
            budget_tokens=context_budget_tokens,
            reserve_tokens=reserve_tokens,
        )
    return payload_messages


async def call_llm_chat(
    messages: list[dict[str, Any]],
    model: str,
    mode: str | None,
    temperature: float,
    max_tokens: int | None,
) -> str:
    base_url = resolve_llm_base_url(mode)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": temperature,
    }
    if isinstance(mode, str) and mode.strip() and mode.strip().lower() != "auto":
        payload["mode"] = mode.strip().lower()
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=build_http_timeout()) as client:
        response = await client.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=build_upstream_headers(),
        )
        response.raise_for_status()
        body = response.json()

    try:
        return str(body["choices"][0]["message"]["content"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Upstream response malformed: {exc}")


async def stream_llm_chat(
    messages: list[dict[str, Any]],
    model: str,
    mode: str | None,
    temperature: float,
    max_tokens: int | None,
) -> Any:
    base_url = resolve_llm_base_url(mode)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": temperature,
        "stream_options": {"include_usage": True},
    }
    if isinstance(mode, str) and mode.strip() and mode.strip().lower() != "auto":
        payload["mode"] = mode.strip().lower()
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    async with httpx.AsyncClient(timeout=build_http_timeout()) as client:
        async with client.stream(
            "POST",
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=build_upstream_headers(),
        ) as response:
            response.raise_for_status()
            if response.headers.get("x-aiui-web-search"):
                yield {"type": "x-status", "text": "Searching the web\u2026"}
            async for line in response.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                payload_text = line[5:].strip()
                if not payload_text or payload_text == "[DONE]":
                    continue
                try:
                    yield json.loads(payload_text)
                except json.JSONDecodeError:
                    continue


async def probe_upstream() -> tuple[bool, str | None]:
    try:
        async with httpx.AsyncClient(timeout=build_health_timeout()) as client:
            response = await client.get(
                f"{FAST_LLM_BASE_URL}/v1/models",
                headers=build_upstream_headers(),
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, format_httpx_error(exc)
    return True, None


app = FastAPI(title="aiui", version="0.3.0")


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/")
def root() -> Any:
    return {
        "status": "ok",
        "service": "aiui-backend",
        "hint": "Use the standalone frontend container on port 3311.",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    upstream_ok, upstream_error = await probe_upstream()
    return {
        "status": "ok",
        "backend": "llama",
        "llm_base_url": LLM_BASE_URL,
        "fast_llm_base_url": FAST_LLM_BASE_URL,
        "default_model": DEFAULT_MODEL,
        "upstream_reachable": upstream_ok,
        "upstream_error": upstream_error,
        "context_budget_tokens": CONTEXT_BUDGET_TOKENS,
    }


@app.get("/modules")
async def modules() -> dict[str, Any]:
    return await load_module_catalog()


@app.post("/chat")
async def chat(req: ChatRequest):
    # Apply rate limiting and attachment abuse guardrails
    check_rate_limit()
    validate_attachments(req.attachments)
    
    text = build_user_text(req.message, req.attachments)
    request_images = normalize_image_attachments(req.attachments)
    if not text and not request_images:
        raise HTTPException(status_code=400, detail="message, image, or document is required")

    module_catalog = await load_module_catalog()
    model = (req.model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    mode, upstream_mode = resolve_request_mode(req.mode, module_catalog)
    payload_messages = build_payload_messages(req, mode=mode)

    if not req.stream:
        try:
            if AGENT_ENABLE_NON_STREAM_LOOP:
                answer = await run_agent_non_stream(
                    messages=payload_messages,
                    model=model,
                    mode=upstream_mode,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                )
            else:
                answer = await call_llm_chat(
                    messages=payload_messages,
                    model=model,
                    mode=upstream_mode,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Upstream chat failed: {format_httpx_error(exc)}") from exc
        return {"message": {"role": "assistant", "content": answer}}

    async def event_stream() -> Any:
        usage: dict[str, Any] = {}
        started_at = time.perf_counter()
        streamed_content_parts: list[str] = []
        tool_specs = build_agent_tool_specs() if AGENT_ENABLE_STREAM_LOOP else []
        agent_messages = inject_tools_into_messages(payload_messages, tool_specs) if tool_specs else payload_messages
        try:
            yield sse_event({"type": "meta", "model": model})
            max_turns = max(1, AGENT_MAX_LLM_CALLS_PER_RUN if AGENT_ENABLE_STREAM_LOOP else 1)
            for turn_index in range(max_turns):
                turn_usage: dict[str, Any] = {}
                turn_tool_parse_buffer = ""
                turn_emitted_tool_calls: list[tuple[str, dict[str, Any]]] = []
                assistant_turn_raw_parts: list[str] = []

                async for upstream_event in stream_llm_chat(
                    messages=agent_messages,
                    model=model,
                    mode=upstream_mode,
                    temperature=req.temperature,
                    max_tokens=req.max_tokens,
                ):
                    if upstream_event.get("type") == "x-status":
                        yield sse_event({"type": "status", "text": upstream_event.get("text", "")})
                        continue

                    event_usage = upstream_event.get("usage")
                    if isinstance(event_usage, dict):
                        turn_usage = event_usage
                        usage = event_usage

                    choices = upstream_event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue

                    first_choice = choices[0] or {}
                    delta = first_choice.get("delta")
                    if isinstance(delta, dict):
                        content_delta = delta.get("content")
                        if isinstance(content_delta, str) and content_delta:
                            assistant_turn_raw_parts.append(content_delta)
                            turn_tool_parse_buffer += content_delta
                            visible_chunks, tool_events, turn_tool_parse_buffer = parse_stream_delta_for_tool_events(
                                turn_tool_parse_buffer
                            )
                            for chunk in visible_chunks:
                                if not chunk:
                                    continue
                                streamed_content_parts.append(chunk)
                                yield sse_event({"type": "token", "delta": chunk})
                            for tool_event in tool_events:
                                yield sse_event(tool_event)
                                name = str(tool_event.get("name") or "")
                                args = tool_event.get("arguments")
                                if name and isinstance(args, dict):
                                    turn_emitted_tool_calls.append((name, args))

                remaining_visible_text = TOOL_CALL_BLOCK_RE.sub("", turn_tool_parse_buffer)
                if remaining_visible_text:
                    streamed_content_parts.append(remaining_visible_text)
                    yield sse_event({"type": "token", "delta": remaining_visible_text})

                assistant_turn_raw = "".join(assistant_turn_raw_parts)
                parsed_tool_calls, _visible_assistant_text = parse_assistant_tool_calls(assistant_turn_raw)

                if len(parsed_tool_calls) > len(turn_emitted_tool_calls):
                    for tool_name, tool_args in parsed_tool_calls[len(turn_emitted_tool_calls) :]:
                        yield sse_event({"type": "tool_call", "name": tool_name, "arguments": tool_args})

                if not AGENT_ENABLE_STREAM_LOOP or not parsed_tool_calls:
                    break

                agent_messages.append({"role": "assistant", "content": assistant_turn_raw})
                for tool_name, tool_args in parsed_tool_calls[: max(1, AGENT_MAX_TOOL_CALLS_PER_TURN)]:
                    tool_result = execute_agent_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        messages=agent_messages,
                    )
                    wrapped_result = {
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": tool_result,
                    }
                    agent_messages.append(make_tool_response_message(wrapped_result))
                    yield sse_event({"type": "tool_result", "name": tool_name, "result": tool_result})

                if turn_index < max_turns - 1:
                    yield sse_event({"type": "status", "text": "continuing after tool results"})
        except httpx.HTTPError as exc:
            yield sse_event({"type": "error", "error": f"Upstream chat failed: {format_httpx_error(exc)}"})
            yield "data: [DONE]\n\n"
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            detail = str(exc).strip() or repr(exc)
            yield sse_event({"type": "error", "error": detail})
            yield "data: [DONE]\n\n"
            return

        elapsed_seconds = max(time.perf_counter() - started_at, 1e-6)
        context_tokens = as_int(usage.get("prompt_tokens"))
        completion_tokens = as_int(usage.get("completion_tokens"))
        total_tokens = as_int(usage.get("total_tokens"))
        if context_tokens <= 0:
            context_tokens = estimate_messages_tokens(agent_messages)
        if completion_tokens <= 0:
            completion_tokens = estimate_text_tokens("".join(streamed_content_parts))
        if total_tokens <= 0:
            # Use explicit integer conversion to avoid type errors
            total_tokens = safe_add_ints(context_tokens, completion_tokens)
        tokens_per_second = (completion_tokens / elapsed_seconds) if completion_tokens > 0 else 0.0

        yield sse_event(
            {
                "type": "done",
                "usage": usage,
                "metrics": {
                    "context_tokens": context_tokens,
                    "tokens": completion_tokens,
                    "tokens_per_second": round(tokens_per_second, 2),
                    "total_tokens": total_tokens,
                    "elapsed_seconds": round(elapsed_seconds, 2),
                },
            }
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.exception_handler(httpx.HTTPError)
async def handle_httpx_error(_request, exc: httpx.HTTPError):
    return JSONResponse(status_code=502, content={"detail": f"Gateway upstream error: {format_httpx_error(exc)}"})
