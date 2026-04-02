"""AIUI attachment models and helpers."""

from __future__ import annotations

import base64
import binascii
import urllib.parse
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from config import MAX_ATTACHMENT_DATA_URL_CHARS, MAX_ATTACHMENTS


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
    agent_tool_profile: str | None = Field(default=None, max_length=32)
    agent_tool_strategy: str | None = Field(default=None, max_length=32)
    agent_enabled_tools: str | None = Field(default=None, max_length=4000)


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


def validate_attachments(attachments: list[Attachment]) -> None:
    """Enforce attachment size and count guardrails to prevent abuse."""
    from fastapi import HTTPException

    if len(attachments) > MAX_ATTACHMENTS:
        raise HTTPException(
            status_code=413,
            detail=f"Too many attachments (max {MAX_ATTACHMENTS}), got {len(attachments)}",
        )
    total_bytes = 0
    for a in attachments:
        if a.data_url:
            try:
                raw = a.data_url.split(",", 1)[-1] if "," in a.data_url else a.data_url
                total_bytes += len(base64.b64decode(raw))
            except (binascii.Error, ValueError):
                pass
    from config import _MAX_ATTACHMENT_BYTES_PER_REQUEST

    if total_bytes > _MAX_ATTACHMENT_BYTES_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment payload too large (max {_MAX_ATTACHMENT_BYTES_PER_REQUEST} bytes), got {total_bytes}",
        )
