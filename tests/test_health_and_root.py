from __future__ import annotations

import app as app_module


def test_root_returns_hint_with_no_cache_header(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "3311" in body.get("hint", "")
    assert "no-store" in response.headers.get("cache-control", "")


def test_health_reports_online_upstream(client, monkeypatch) -> None:
    async def fake_probe_upstream() -> tuple[bool, str | None]:
        return True, None

    monkeypatch.setattr(app_module, "probe_upstream", fake_probe_upstream)

    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert body["backend"] == "llama"
    assert body["default_model"] == app_module.DEFAULT_MODEL
    assert body["llm_base_url"] == app_module.LLM_BASE_URL
    assert body["upstream_reachable"] is True
    assert body["upstream_error"] is None


def test_health_reports_upstream_error(client, monkeypatch) -> None:
    async def fake_probe_upstream() -> tuple[bool, str | None]:
        return False, "ConnectError: could not connect to upstream"

    monkeypatch.setattr(app_module, "probe_upstream", fake_probe_upstream)

    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()

    assert body["upstream_reachable"] is False
    assert "could not connect" in body["upstream_error"]


def test_fallback_module_catalog_exposes_only_core_chat() -> None:
    body = app_module.build_fallback_module_catalog(upstream_error="HTTP 404")

    assert body["default_mode"] == "chat"
    assert body["core_mode"] == "chat"
    assert body["source"] == "fallback"
    assert body["upstream_error"] == "HTTP 404"
    assert body["modes"] == [
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
    ]


def test_modules_route_returns_loaded_catalog(client, monkeypatch) -> None:
    async def fake_load_module_catalog() -> dict[str, object]:
        return {
            "service": "orchestrator",
            "version": "v1",
            "default_mode": "chat",
            "core_mode": "chat",
            "source": "upstream",
            "modes": [
                {
                    "id": "chat",
                    "route": "chat_core",
                    "label": "Chat",
                    "description": "Primary chat lane on 8081.",
                    "primary_lane": "chat_core",
                    "kind": "core",
                    "selection": "default",
                    "user_selectable": True,
                },
                {
                    "id": "library",
                    "route": "academic_rag",
                    "label": "Library",
                    "description": "Saved Parker corpus.",
                    "primary_lane": "academic_rag",
                    "kind": "add_in",
                    "selection": "explicit",
                    "user_selectable": True,
                },
            ],
        }

    monkeypatch.setattr(app_module, "load_module_catalog", fake_load_module_catalog)

    response = client.get("/modules")
    assert response.status_code == 200
    body = response.json()

    assert body["source"] == "upstream"
    assert body["core_mode"] == "chat"
    assert [item["id"] for item in body["modes"]] == ["chat", "library"]
