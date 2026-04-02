"""AIUI context budgeting — token estimation, message trimming, and context summary building."""

from __future__ import annotations

import math
from typing import Any

from config import IMAGE_PART_TOKEN_ESTIMATE, RESPONSE_FORMAT_GUIDANCE


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
        int_a = int(a) if a is not None else 0
        int_b = int(b) if b is not None else 0
        return int_a + int_b
    except (TypeError, ValueError):
        return 0


def as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(str(value))
        except (TypeError, ValueError):
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

    lead_system: list[dict[str, Any]] = []
    remaining = list(messages)
    while remaining and str(remaining[0].get("role") or "").strip().lower() == "system":
        lead_system.append(remaining.pop(0))

    if not remaining:
        return lead_system

    system_tokens = estimate_messages_tokens(lead_system) if lead_system else 0
    remaining_budget = max(0, budget_tokens - system_tokens)
    if remaining_budget <= 0:
        return lead_system + [remaining[-1]]

    kept, _dropped = split_messages_by_context_budget(
        remaining,
        budget_tokens=remaining_budget,
        reserve_tokens=reserve_tokens,
    )
    return lead_system + kept


def build_summary_system_prompt(system_prompt: str, context_summary: str) -> str:
    cleaned_system_prompt = str(system_prompt or "").strip()
    cleaned_context_summary = str(context_summary or "").strip()

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


def combine_context_summaries(*summaries: str) -> str:
    parts = [str(summary or "").strip() for summary in summaries if str(summary or "").strip()]
    return "\n\n".join(parts)
