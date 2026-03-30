from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

NOMIC_SEARCH_PATH = Path.home() / ".qwen" / "tools" / "nomic_search.py"


def _load_module():
    if not NOMIC_SEARCH_PATH.is_file():
        pytest.skip(f"nomic_search.py not found at {NOMIC_SEARCH_PATH}")
    spec = importlib.util.spec_from_file_location("nomic_search", str(NOMIC_SEARCH_PATH))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semantic_search_skips_swift_build_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = _load_module()

    (tmp_path / "Sources").mkdir()
    (tmp_path / ".build").mkdir()
    (tmp_path / ".swiftpm").mkdir()
    (tmp_path / "DerivedData").mkdir()

    (tmp_path / "Sources" / "GameScene.swift").write_text("class GameScene {}\n", encoding="utf-8")
    (tmp_path / ".build" / "output-file-map.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".swiftpm" / "state.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "DerivedData" / "meta.json").write_text("{}\n", encoding="utf-8")

    def fake_embed_batch(texts: list[str]):
        return [[1.0] for _ in texts], "/v1/embeddings"

    monkeypatch.setattr(mod, "_embed_batch", fake_embed_batch)

    result = mod.semantic_search("game mechanics", str(tmp_path), 10)

    assert "error" not in result
    files = [item["file"] for item in result["results"]]
    assert "Sources/GameScene.swift" in files
    assert all(not item.startswith(".build/") for item in files)
    assert all(not item.startswith(".swiftpm/") for item in files)
    assert all(not item.startswith("DerivedData/") for item in files)


def test_semantic_search_adapts_embed_input_chars_on_token_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = _load_module()

    (tmp_path / "src").mkdir()
    for idx in range(3):
        (tmp_path / "src" / f"file_{idx}.py").write_text(
            "# token-heavy\n" + ("word " * 200), encoding="utf-8"
        )

    call_count = {"n": 0}

    def flaky_embed_batch(texts: list[str]):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None, (
                '/v1/embeddings: HTTP 500 {"error":{"message":"input (513 tokens) '
                'is too large to process. increase the physical batch size (current '
                'batch size: 512)"}}'
            )
        return [[1.0] for _ in texts], "/v1/embeddings"

    monkeypatch.setattr(mod, "_embed_batch", flaky_embed_batch)

    result = mod.semantic_search("movement collision", str(tmp_path), 5)

    assert "error" not in result
    assert result["embed_input_chars_used"] < max(120, mod.EMBED_INPUT_CHARS)
    assert result["files_embedded"] >= 1


def test_semantic_search_returns_expected_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = _load_module()

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("architecture overview\n", encoding="utf-8")

    def fake_embed_batch(texts: list[str]):
        return [[1.0] for _ in texts], "/v1/embeddings"

    monkeypatch.setattr(mod, "_embed_batch", fake_embed_batch)

    result = mod.semantic_search("architecture overview", str(tmp_path), 3)

    expected_keys = {
        "query",
        "repo_path",
        "files_considered",
        "files_ranked",
        "files_embedded",
        "embed_input_chars_used",
        "endpoint_used",
        "nomic_url",
        "model",
        "directory_overview",
        "results",
    }
    assert expected_keys.issubset(result.keys())
    assert isinstance(result["directory_overview"], list)
    assert isinstance(result["results"], list)
