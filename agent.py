"""AIUI agent — tool orchestration, tool call parsing, and agent loop."""

from __future__ import annotations

import copy
import json
from typing import Any

from config import (
    AGENT_MAX_LLM_CALLS_PER_RUN,
    AGENT_MAX_TOOL_CALLS_PER_TURN,
    TOOL_CALL_BLOCK_RE,
)
from tools import ToolError, ToolManager


def build_agent_tool_specs(tool_manager: ToolManager) -> list[dict[str, Any]]:
    return [schema.get("function", {}) for schema in tool_manager.get_tool_schemas()]


def build_nous_tools_instruction(tool_specs: list[dict[str, Any]], tool_manager: ToolManager) -> str:
    _ = tool_specs
    return tool_manager.get_tools_instruction()


def inject_tools_into_messages(
    messages: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
    tool_manager: ToolManager,
) -> list[dict[str, Any]]:
    if not tool_specs:
        return messages

    out = copy.deepcopy(messages)
    tool_instruction = tool_manager.get_tools_instruction()

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


def parse_assistant_tool_calls(
    text: str,
    tool_manager: ToolManager,
) -> tuple[list[tuple[str, dict[str, Any]]], str]:
    if not text:
        return [], ""

    calls: list[tuple[str, dict[str, Any]]] = []
    parsed_calls = tool_manager.parse_tool_calls(text)
    for call in parsed_calls:
        name = str(call.get("name") or "").strip()
        args = call.get("arguments")
        if name and isinstance(args, dict):
            calls.append((name, args))

    if not calls:
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


def execute_agent_tool(
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_manager: ToolManager,
) -> dict[str, Any]:
    kwargs = dict(tool_args or {})
    if tool_name == "search_conversation":
        kwargs["conversation_messages"] = messages
    try:
        raw_result = tool_manager.execute_tool(tool_name, **kwargs)
    except ToolError as exc:
        return {"error": f"{exc.code}: {exc.message}"}
    except Exception as exc:
        return {"error": str(exc)}

    if isinstance(raw_result, str):
        text = raw_result.strip()
        if not text:
            return {"result": ""}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"result": text}
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    if isinstance(raw_result, dict):
        return raw_result
    return {"result": raw_result}


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
    tool_manager: ToolManager,
    call_llm_chat,
) -> str:
    tool_specs = build_agent_tool_specs(tool_manager)
    working_messages = inject_tools_into_messages(messages, tool_specs, tool_manager)

    last_visible_text = ""
    for _ in range(max(1, AGENT_MAX_LLM_CALLS_PER_RUN)):
        assistant_text = await call_llm_chat(
            messages=working_messages,
            model=model,
            mode=mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        tool_calls, visible_text = parse_assistant_tool_calls(assistant_text, tool_manager)
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
                tool_manager=tool_manager,
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
