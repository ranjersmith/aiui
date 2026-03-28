from __future__ import annotations

import app as app_module


def test_apply_context_budget_keeps_system_and_latest_message() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "a" * 500},
        {"role": "assistant", "content": "b" * 500},
        {"role": "user", "content": "latest"},
    ]

    trimmed = app_module.apply_context_budget(messages, budget_tokens=20, reserve_tokens=0)

    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"] == "latest"
    assert len(trimmed) < len(messages)


def test_chat_non_stream_applies_context_budget(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(messages, model, mode, temperature, max_tokens):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "SYSTEM")
    monkeypatch.setattr(app_module, "CONTEXT_BUDGET_TOKENS", 20)
    monkeypatch.setattr(app_module, "CONTEXT_REPLY_RESERVE_TOKENS", 0)

    response = client.post(
        "/chat",
        json={
            "message": "final question",
            "history": [
                {"role": "user", "content": "u" * 600},
                {"role": "assistant", "content": "a" * 600},
                {"role": "user", "content": "keep me maybe"},
            ],
            "stream": False,
            "max_tokens": 1,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "final question"
    assert len(messages) < 5


def test_chat_non_stream_allows_disabling_context_budget_per_request(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(messages, model, mode, temperature, max_tokens):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")
    monkeypatch.setattr(app_module, "CONTEXT_BUDGET_TOKENS", 20)
    monkeypatch.setattr(app_module, "CONTEXT_REPLY_RESERVE_TOKENS", 0)

    response = client.post(
        "/chat",
        json={
            "message": "latest",
            "history": [
                {"role": "user", "content": "u" * 600},
                {"role": "assistant", "content": "a" * 600},
                {"role": "user", "content": "keep me too"},
            ],
            "stream": False,
            "context_budget_tokens": 0,
            "max_tokens": 1,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1:] == [
        {"role": "user", "content": "u" * 600},
        {"role": "assistant", "content": "a" * 600},
        {"role": "user", "content": "keep me too"},
        {"role": "user", "content": "latest"},
    ]
