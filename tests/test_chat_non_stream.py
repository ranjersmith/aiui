from __future__ import annotations

import httpx

import app as app_module


def test_chat_rejects_blank_message(client) -> None:
    response = client.post("/chat", json={"message": "   ", "history": [], "stream": False})
    assert response.status_code == 400
    assert response.json()["detail"] == "message, image, or document is required"


def test_chat_rejects_invalid_history_role(client) -> None:
    response = client.post(
        "/chat",
        json={
            "message": "hello",
            "history": [{"role": "system", "content": "bad role"}],
            "stream": False,
        },
    )
    assert response.status_code == 422


def test_chat_non_stream_success_builds_payload_and_returns_answer(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        captured["model"] = model
        captured["mode"] = mode
        captured["temperature"] = temperature
        captured["max_tokens"] = max_tokens
        return "Answer from fake upstream"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "SYSTEM TEST PROMPT")

    response = client.post(
        "/chat",
        json={
            "message": "What is 2+2?",
            "history": [
                {"role": "user", "content": "  previous user  "},
                {"role": "assistant", "content": " previous assistant "},
                {"role": "assistant", "content": "   "},
            ],
            "model": "custom-model",
            "stream": False,
            "temperature": 0.25,
            "max_tokens": 32,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": {"role": "assistant", "content": "Answer from fake upstream"}}

    assert captured["model"] == "custom-model"
    assert captured["mode"] == "chat"
    assert captured["temperature"] == 0.25
    assert captured["max_tokens"] == 32
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith("SYSTEM TEST PROMPT\n")
    assert "Today's date" in messages[0]["content"]
    assert messages[1:] == [
        {"role": "user", "content": "previous user"},
        {"role": "assistant", "content": "previous assistant"},
        {"role": "user", "content": "What is 2+2?"},
    ]


def test_chat_non_stream_returns_502_on_upstream_error(client, monkeypatch) -> None:
    async def fake_call_llm_chat(*_args, **_kwargs) -> str:
        request = httpx.Request("POST", "http://unit-test-upstream/v1/chat/completions")
        raise httpx.ConnectError("connection failed", request=request)

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)

    response = client.post("/chat", json={"message": "hello", "history": [], "stream": False})
    assert response.status_code == 502
    assert "Upstream chat failed" in response.json()["detail"]


def test_chat_non_stream_merges_context_summary_into_system_prompt(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "SYSTEM BASE")

    response = client.post(
        "/chat",
        json={
            "message": "latest question",
            "history": [{"role": "user", "content": "newer context"}],
            "context_summary": "- user: older point",
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "SYSTEM BASE" in messages[0]["content"]
    assert "Older conversation summary" in messages[0]["content"]
    assert "- user: older point" in messages[0]["content"]


def test_chat_non_stream_builds_server_side_summary_when_requested(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "SYSTEM BASE")
    monkeypatch.setattr(app_module, "CONTEXT_BUDGET_TOKENS", 260)
    monkeypatch.setattr(app_module, "CONTEXT_REPLY_RESERVE_TOKENS", 0)

    response = client.post(
        "/chat",
        json={
            "message": "latest question",
            "history": [
                {"role": "user", "content": "u" * 500},
                {"role": "assistant", "content": "a" * 500},
                {"role": "user", "content": "keep this recent turn"},
            ],
            "context_mode": "summarize",
            "stream": False,
            "max_tokens": 1,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "SYSTEM BASE" in messages[0]["content"]
    assert "Today's date" in messages[0]["content"]
    assert "Older conversation summary" in messages[0]["content"]
    assert "keep this recent turn" not in messages[0]["content"]
    assert messages[-1]["content"] == "latest question"


def test_chat_non_stream_allows_image_only_prompt(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={
            "message": "",
            "attachments": [
                {
                    "type": "image",
                    "data_url": "data:image/png;base64,ZmFrZS1iaW5hcnk=",
                }
            ],
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    # Even with no SYSTEM_PROMPT, the date line is injected as the first system message.
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1:] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,ZmFrZS1iaW5hcnk="},
                }
            ],
        }
    ]


def test_chat_non_stream_allows_document_only_prompt(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={
            "message": "",
            "attachments": [
                {
                    "type": "document",
                    "name": "notes.txt",
                    "mime_type": "text/plain",
                    "data_url": "data:text/plain;base64,SGVsbG8gZnJvbSBhIHRleHQgZG9jdW1lbnQu",
                }
            ],
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1:] == [
        {
            "role": "user",
            "content": "Attached documents:\n\n[Attached document: notes.txt]\nHello from a text document.",
        }
    ]


def test_chat_non_stream_serializes_history_images_for_user_turns(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={
            "message": "current question",
            "history": [
                {
                    "role": "user",
                    "content": "look at this",
                    "attachments": [
                        {
                            "type": "image",
                            "data_url": "data:image/jpeg;base64,ZmFrZS1wZWc=",
                        }
                    ],
                },
                {"role": "assistant", "content": "I can see it"},
            ],
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "look at this"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,ZmFrZS1wZWc="}},
        ],
    }
    assert messages[2] == {"role": "assistant", "content": "I can see it"}


def test_chat_non_stream_serializes_history_documents_for_user_turns(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={
            "message": "summarize it",
            "history": [
                {
                    "role": "user",
                    "content": "please use this",
                    "attachments": [
                        {
                            "type": "document",
                            "name": "outline.md",
                            "mime_type": "text/markdown",
                            "data_url": "data:text/markdown;base64,IyBUaXRsZQoKLSBmaXJzdAotIHNlY29uZAo=",
                        }
                    ],
                }
            ],
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1] == {
        "role": "user",
        "content": "please use this\n\nAttached documents:\n\n[Attached document: outline.md]\n# Title\n- first\n- second",
    }
    assert messages[2] == {"role": "user", "content": "summarize it"}


def test_chat_non_stream_accepts_dynamic_mode_ids_from_module_catalog(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["mode"] = mode
        return "ok"

    async def fake_load_module_catalog() -> dict[str, object]:
        return {
            "service": "orchestrator",
            "version": "v1",
            "source": "upstream",
            "default_mode": "chat",
            "core_mode": "chat",
            "modes": [
                {"id": "chat", "user_selectable": True},
                {"id": "news", "user_selectable": False},
            ],
        }

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "load_module_catalog", fake_load_module_catalog)

    response = client.post(
        "/chat",
        json={
            "message": "latest headlines please",
            "mode": "news",
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert captured["mode"] == "news"


def test_chat_non_stream_omits_mode_when_module_catalog_is_fallback(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["mode"] = mode
        return "ok"

    async def fake_load_module_catalog() -> dict[str, object]:
        return app_module.build_fallback_module_catalog(upstream_error="offline")

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "load_module_catalog", fake_load_module_catalog)

    response = client.post(
        "/chat",
        json={
            "message": "hello",
            "mode": "chat",
            "stream": False,
        },
    )

    assert response.status_code == 200
    assert captured["mode"] is None


def test_chat_non_stream_drops_library_style_assistant_history_in_auto_mode(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    response = client.post(
        "/chat",
        json={
            "message": "Write me a 500 word story about a lighthouse keeper who hears music in the fog.",
            "history": [
                {"role": "user", "content": "Find some healing-story references."},
                {
                    "role": "assistant",
                    "content": (
                        "I found some promising references.\n\n"
                        "Evidence:\n"
                        "- [E1] Healing Stories for Kids and Teens\n"
                        "- [E2] Writing Your Own Story"
                    ),
                },
            ],
            "mode": "auto",
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1:] == [
        {"role": "user", "content": "Find some healing-story references."},
        {
            "role": "user",
            "content": "Write me a 500 word story about a lighthouse keeper who hears music in the fog.",
        },
    ]


def test_chat_non_stream_keeps_library_style_assistant_history_in_library_mode(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "")

    library_reply = (
        "I found some promising references.\n\n"
        "Evidence:\n"
        "- [E1] Healing Stories for Kids and Teens\n"
        "- [E2] Writing Your Own Story"
    )

    response = client.post(
        "/chat",
        json={
            "message": "Keep searching the saved corpus.",
            "history": [
                {"role": "user", "content": "Find some healing-story references."},
                {"role": "assistant", "content": library_reply},
            ],
            "mode": "library",
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert "Today's date" in messages[0]["content"]
    assert messages[1:] == [
        {"role": "user", "content": "Find some healing-story references."},
        {"role": "assistant", "content": library_reply},
        {"role": "user", "content": "Keep searching the saved corpus."},
    ]


def test_chat_non_stream_strips_library_lines_from_context_summary_in_auto_mode(client, monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_llm_chat(
        messages: list[dict[str, object]],
        model: str,
        mode: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> str:
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(app_module, "call_llm_chat", fake_call_llm_chat)
    monkeypatch.setattr(app_module, "SYSTEM_PROMPT", "SYSTEM BASE")

    response = client.post(
        "/chat",
        json={
            "message": "Write a short story about a moonlit harbor.",
            "context_summary": (
                "Older conversation summary (latest trimmed turns):\n"
                "- assistant: Here are some saved-corpus hits. Evidence: - [E1] Healing Stories - [E2] Writing Your Own Story\n"
                "- user: now write something original"
            ),
            "mode": "auto",
            "stream": False,
        },
    )

    assert response.status_code == 200
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "SYSTEM BASE" in messages[0]["content"]
    assert "now write something original" in messages[0]["content"]
    assert "[E1]" not in messages[0]["content"]
    assert "saved-corpus hits" not in messages[0]["content"]
