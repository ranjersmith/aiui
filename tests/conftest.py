from __future__ import annotations

from collections.abc import Iterator
import importlib
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure imports work even when pytest is launched outside the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

app_module = importlib.import_module("app")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def stub_module_catalog(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def fake_load_module_catalog() -> dict[str, object]:
        return {
            "service": "orchestrator",
            "version": "v1",
            "source": "upstream",
            "default_mode": "chat",
            "core_mode": "chat",
            "modes": [
                {"id": "chat", "user_selectable": True},
                {"id": "auto", "user_selectable": False},
                {"id": "vision", "user_selectable": True},
                {"id": "image", "user_selectable": True},
                {"id": "coder", "user_selectable": True},
                {"id": "library", "user_selectable": True},
                {"id": "news", "user_selectable": False},
            ],
        }

    monkeypatch.setattr(app_module, "load_module_catalog", fake_load_module_catalog)
    app_module._MODULE_CATALOG_CACHE["body"] = None
    app_module._MODULE_CATALOG_CACHE["expires_at"] = 0.0
    yield
