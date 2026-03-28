from __future__ import annotations

import json
from typing import Any, cast

import httpx

import app as app_module


def _decode_sse_payloads(body: str) -> list[str]:
    payloads: list[str] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            payloads.append(line[5:].strip())
    return payloads


def _json_events(payloads: list[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for payload in payloads:
        if not payload or payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


def test_chat_stream_emits_meta_tokens_done_with_metrics(client, monkeypatch) -> None:
    async def fake_stream_llm_chat(*_args, **_kwargs):
        yield {"choices": [{"delta": {"content": "Hel"}}]}
        yield {
            "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
            "choices": [{"delta": {"content": "lo"}}],
        }

    monkeypatch.setattr(app_module, "stream_llm_chat", fake_stream_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={"message": "say hello", "history": [], "stream": True, "temperature": 0.4},
    )

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/event-stream")

    payloads = _decode_sse_payloads(response.text)
    assert payloads[-1] == "[DONE]"

    events = _json_events(payloads)
    assert events[0] == {"type": "meta", "model": app_module.DEFAULT_MODEL}

    token_events = [evt for evt in events if evt.get("type") == "token"]
    assert "".join(str(evt["delta"]) for evt in token_events) == "Hello"

    done_events = [evt for evt in events if evt.get("type") == "done"]
    assert len(done_events) == 1
    done = done_events[0]

    metrics = cast(dict[str, Any], done["metrics"])
    assert metrics["context_tokens"] == 7
    assert metrics["tokens"] == 2
    assert metrics["total_tokens"] == 9
    assert metrics["tokens_per_second"] >= 0


def test_chat_stream_emits_error_event_on_upstream_failure(client, monkeypatch) -> None:
    async def fake_stream_llm_chat(*_args, **_kwargs):
        request = httpx.Request("POST", "http://unit-test-upstream/v1/chat/completions")
        raise httpx.ConnectError("connection failed", request=request)
        yield {}  # pragma: no cover

    monkeypatch.setattr(app_module, "stream_llm_chat", fake_stream_llm_chat)

    response = client.post("/chat", json={"message": "hello", "history": [], "stream": True})

    assert response.status_code == 200
    payloads = _decode_sse_payloads(response.text)
    assert payloads[-1] == "[DONE]"

    events = _json_events(payloads)
    event_types = [evt.get("type") for evt in events]
    assert "meta" in event_types
    assert "error" in event_types

    error_event = next(evt for evt in events if evt.get("type") == "error")
    assert "could not connect to upstream" in str(error_event.get("error", ""))


def test_chat_stream_estimates_metrics_when_upstream_usage_missing(client, monkeypatch) -> None:
    async def fake_stream_llm_chat(*_args, **_kwargs):
        yield {"choices": [{"delta": {"content": "Book"}}]}
        yield {"choices": [{"delta": {"content": " icon"}}]}

    monkeypatch.setattr(app_module, "stream_llm_chat", fake_stream_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={
            "message": "What is in this image?",
            "attachments": [{"type": "image", "data_url": "data:image/png;base64,AAAA"}],
            "history": [],
            "stream": True,
            "temperature": 0.1,
        },
    )

    assert response.status_code == 200
    payloads = _decode_sse_payloads(response.text)
    events = _json_events(payloads)
    done = next(evt for evt in events if evt.get("type") == "done")

    metrics = cast(dict[str, Any], done["metrics"])
    assert metrics["context_tokens"] >= app_module.IMAGE_PART_TOKEN_ESTIMATE
    assert metrics["tokens"] == 3
    assert metrics["total_tokens"] == metrics["context_tokens"] + metrics["tokens"]
    assert metrics["tokens_per_second"] >= 0


def test_chat_stream_allows_document_only_prompt(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_stream_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ):
        captured["messages"] = messages
        yield {"choices": [{"delta": {"content": "done"}}]}

    monkeypatch.setattr(app_module, "stream_llm_chat", fake_stream_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={
            "message": "",
            "attachments": [
                {
                    "type": "document",
                    "name": "brief.txt",
                    "mime_type": "text/plain",
                    "data_url": "data:text/plain;base64,RG9jdW1lbnQgYm9keS4=",
                }
            ],
            "history": [],
            "stream": True,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1] == {
        "role": "user",
        "content": "Attached documents:\n\n[Attached document: brief.txt]\nDocument body.",
    }
