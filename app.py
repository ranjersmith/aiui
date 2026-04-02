"""AIUI — FastAPI backend: routes, LLM proxy, SSE streaming, and application wiring."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from tools import ToolError, ToolManager, list_strategies  # noqa: F401 (re-exported)

# ── Re-export everything from config so existing tests (`import app as app_module`) keep working.
from config import (  # noqa: F401
    env_bool,
    env_int,
    env_float,
    LLM_BASE_URL,
    DEFAULT_MODEL,
    REQUEST_TIMEOUT_SECONDS,
    SYSTEM_PROMPT,
    RESPONSE_FORMAT_GUIDANCE,
    DEFAULT_API_KEY,
    UPSTREAM_HEALTH_TIMEOUT_SECONDS,
    CONTEXT_BUDGET_TOKENS,
    CONTEXT_REPLY_RESERVE_TOKENS,
    MODULE_CATALOG_CACHE_TTL_SECONDS,
    AGENT_MAX_LLM_CALLS_PER_RUN,
    AGENT_MAX_TOOL_CALLS_PER_TURN,
    AGENT_ENABLE_NON_STREAM_LOOP,
    AGENT_ENABLE_STREAM_LOOP,
    AGENT_TOOL_PROFILE,
    AGENT_TOOL_STRATEGY,
    AGENT_ENABLED_TOOLS_RAW,
    ENABLE_EXTERNAL_EXTRACTORS,
    MAX_ATTACHMENTS,
    MAX_ATTACHMENT_DATA_URL_CHARS,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_TEXT_CHARS,
    MAX_TOTAL_DOCUMENT_TEXT_CHARS,
    IMAGE_PART_TOKEN_ESTIMATE,
    PARKER_EVIDENCE_LABEL_RE,
    PARKER_EVIDENCE_BULLET_RE,
    TOOL_CALL_BLOCK_RE,
    THINK_BLOCK_RE,
    _REQUEST_TIMESTAMPS,
    _MAX_REQUESTS_PER_SECOND,
    _MAX_ATTACHMENT_BYTES_PER_REQUEST,
    _MODULE_CATALOG_CACHE,
    DEFAULT_AGENT_TOOL_NAMES,
    SAFE_AGENT_TOOL_NAMES,
    MINIMAL_AGENT_TOOL_NAMES,
    AGENT_TOOL_PROFILES,
    AGENT_ALLOWED_STRATEGIES,
    TEXT_DOCUMENT_EXTENSIONS,
    WORDPROCESSINGML_NAMESPACE,
    DRAWINGML_TEXT_TAG,
)

from attachments import (  # noqa: F401
    Attachment,
    HistoryMessage,
    ChatRequest,
    attachment_name,
    decode_attachment_data_url,
    normalize_image_attachments,
    validate_attachments,
)

from extraction import (  # noqa: F401
    normalize_document_text,
    decode_text_document,
    extract_docx_text,
    extract_pptx_text,
    extract_pdf_text,
    run_external_document_extractor,
    extract_document_text,
    build_document_context,
)

from context import (  # noqa: F401
    compact_text,
    estimate_text_tokens,
    estimate_content_tokens,
    estimate_messages_tokens,
    extract_summary_text,
    count_summary_images,
    build_context_summary,
    safe_add_ints,
    as_int,
    select_context_budget_indices,
    split_messages_by_context_budget,
    apply_context_budget,
    build_summary_system_prompt,
    combine_context_summaries,
)

from agent import (  # noqa: F401
    build_agent_tool_specs,
    build_nous_tools_instruction,
    inject_tools_into_messages,
    parse_assistant_tool_calls,
    parse_stream_delta_for_tool_events,
    execute_agent_tool,
    make_tool_response_message,
    run_agent_non_stream,
)

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


# ── Tool manager initialisation ────────────────────────────────────────────

def _parse_enabled_tool_names(raw: str) -> list[str] | None:
    value = str(raw or "").strip()
    if not value:
        return None
    if value.lower() in {"all", "trusted"}:
        return None
    names = [item.strip() for item in value.split(",") if item.strip()]
    return names or None


def _strategy_or_default(value: str | None, default: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in AGENT_ALLOWED_STRATEGIES:
        return candidate
    return default


def _profile_or_default(value: str | None, default: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in AGENT_TOOL_PROFILES:
        return candidate
    return default


def _resolve_tool_names(profile: str, enabled_tools_raw: str) -> list[str] | None:
    explicit = _parse_enabled_tool_names(enabled_tools_raw)
    if explicit is not None:
        return explicit
    profile_names = AGENT_TOOL_PROFILES.get(profile)
    if profile_names is None:
        return None
    return list(profile_names)


def _init_tool_manager(
    *,
    profile: str | None = None,
    strategy: str | None = None,
    enabled_tools_raw: str | None = None,
) -> ToolManager:
    resolved_profile = _profile_or_default(profile, AGENT_TOOL_PROFILE)
    resolved_strategy = _strategy_or_default(strategy, AGENT_TOOL_STRATEGY)
    names = _resolve_tool_names(resolved_profile, enabled_tools_raw or AGENT_ENABLED_TOOLS_RAW)
    try:
        return ToolManager(tool_names=names, strategy=resolved_strategy)
    except Exception as exc:
        logger.warning(
            "ToolManager init failed; using safe fallback profile=%s strategy=%s error=%s",
            resolved_profile,
            resolved_strategy,
            str(exc),
        )
        fallback_names = names or AGENT_TOOL_PROFILES["safe"] or DEFAULT_AGENT_TOOL_NAMES
        try:
            return ToolManager(tool_names=fallback_names, strategy="nous")
        except Exception as fallback_exc:
            logger.error(
                "ToolManager safe fallback failed; using minimal fallback error=%s",
                str(fallback_exc),
            )
            return ToolManager(tool_names=["get_current_time", "calculator", "search_conversation"], strategy="nous")


AGENT_TOOL_MANAGER = _init_tool_manager(
    profile=AGENT_TOOL_PROFILE,
    strategy=AGENT_TOOL_STRATEGY,
    enabled_tools_raw=AGENT_ENABLED_TOOLS_RAW,
)


def resolve_tool_manager_for_request(req: ChatRequest) -> ToolManager:
    return _init_tool_manager(
        profile=req.agent_tool_profile,
        strategy=req.agent_tool_strategy,
        enabled_tools_raw=req.agent_enabled_tools,
    )


# ── HTTP helpers ───────────────────────────────────────────────────────────

def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


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


def check_rate_limit() -> None:
    now = time.perf_counter()
    _REQUEST_TIMESTAMPS[:] = [t for t in _REQUEST_TIMESTAMPS if now - t < 1.0]
    if len(_REQUEST_TIMESTAMPS) >= _MAX_REQUESTS_PER_SECOND:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _REQUEST_TIMESTAMPS.append(now)


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


# ── Module catalog ─────────────────────────────────────────────────────────

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


# ── Message building ───────────────────────────────────────────────────────

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


def normalize_history(history: list[HistoryMessage], *, mode: str = "chat") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in history:
        text = build_user_text(item.content, item.attachments)
        if item.role == "assistant":
            if not text:
                continue
            text = THINK_BLOCK_RE.sub("", text).strip()
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


# ── LLM call functions ────────────────────────────────────────────────────

async def call_llm_chat(
    messages: list[dict[str, Any]],
    model: str,
    mode: str | None,
    temperature: float,
    max_tokens: int | None,
) -> str:
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
            f"{LLM_BASE_URL}/v1/chat/completions",
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
            f"{LLM_BASE_URL}/v1/chat/completions",
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
                f"{LLM_BASE_URL}/v1/models",
                headers=build_upstream_headers(),
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        return False, format_httpx_error(exc)
    return True, None


# ── FastAPI application ────────────────────────────────────────────────────

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
        "default_model": DEFAULT_MODEL,
        "upstream_reachable": upstream_ok,
        "upstream_error": upstream_error,
        "context_budget_tokens": CONTEXT_BUDGET_TOKENS,
        "agent_tool_profile": AGENT_TOOL_PROFILE,
        "agent_tool_strategy": AGENT_TOOL_STRATEGY,
        "agent_tool_count": len(AGENT_TOOL_MANAGER.tool_names),
        "agent_tools": list(AGENT_TOOL_MANAGER.tool_names),
    }


@app.get("/modules")
async def modules() -> dict[str, Any]:
    return await load_module_catalog()


@app.post("/chat")
async def chat(req: ChatRequest):
    check_rate_limit()
    validate_attachments(req.attachments)

    text = build_user_text(req.message, req.attachments)
    request_images = normalize_image_attachments(req.attachments)
    if not text and not request_images:
        raise HTTPException(status_code=400, detail="message, image, or document is required")

    module_catalog = await load_module_catalog()
    request_tool_manager = resolve_tool_manager_for_request(req)
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
                    tool_manager=request_tool_manager,
                    call_llm_chat=call_llm_chat,
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
        tool_specs = build_agent_tool_specs(request_tool_manager) if AGENT_ENABLE_STREAM_LOOP else []
        agent_messages = (
            inject_tools_into_messages(payload_messages, tool_specs, request_tool_manager)
            if tool_specs
            else payload_messages
        )
        try:
            yield sse_event({"type": "meta", "model": model})
            max_turns = max(1, AGENT_MAX_LLM_CALLS_PER_RUN if AGENT_ENABLE_STREAM_LOOP else 1)
            for turn_index in range(max_turns):
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
                parsed_tool_calls, _visible_assistant_text = parse_assistant_tool_calls(
                    assistant_turn_raw,
                    request_tool_manager,
                )

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
                        tool_manager=request_tool_manager,
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
