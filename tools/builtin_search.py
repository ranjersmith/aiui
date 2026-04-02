"""Semantic search tool using Nomic embeddings and optional reranker.

Bridges AIUI's agent to the embedding (:8083) and reranker (:8084) HTTP services.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

from .base import BaseTool, register_tool, ToolError

logger = logging.getLogger(__name__)

NOMIC_EMBED_URL = os.getenv("NOMIC_EMBED_URL", "http://127.0.0.1:8083")
NOMIC_MODEL = os.getenv("NOMIC_MODEL", "nomic-embed-text-v2-moe")
RERANKER_URL = os.getenv("RERANKER_URL", "http://127.0.0.1:8084")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "qwen3-reranker")
EMBED_TIMEOUT = 30
RERANKER_TIMEOUT = 15
MAX_FILE_CHARS = 4000
MAX_FILES_TO_EMBED = 80
TOP_K = 10

WORKSPACE_ROOT = os.getenv("AIUI_WORKSPACE_ROOT", os.getcwd())

# File extensions to index for semantic search.
CODE_EXTENSIONS = frozenset({
    ".py", ".ts", ".js", ".tsx", ".jsx", ".mjs", ".mts",
    ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".sh", ".bash", ".zsh",
    ".sql", ".yaml", ".yml", ".toml", ".json",
    ".md", ".txt", ".css", ".html",
})

SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", ".next", "vendor",
})


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def _embed(texts: list[str]) -> list[list[float]] | None:
    """Embed a batch of texts via the nomic embedding endpoint."""
    if not texts:
        return []
    url = f"{NOMIC_EMBED_URL}/v1/embeddings"
    try:
        body = _post_json(url, {"model": NOMIC_MODEL, "input": texts}, EMBED_TIMEOUT)
    except Exception as exc:
        logger.warning("Embedding request failed: %s", exc)
        return None
    items = body.get("data", [])
    if not isinstance(items, list):
        return None
    ordered = sorted(items, key=lambda x: int(x.get("index", 0)) if isinstance(x, dict) else 0)
    vectors: list[list[float]] = []
    for item in ordered:
        emb = item.get("embedding") if isinstance(item, dict) else None
        if isinstance(emb, list) and emb and isinstance(emb[0], (int, float)):
            vectors.append(emb)
    return vectors if len(vectors) == len(texts) else None


def _rerank(query: str, documents: list[str], top_n: int) -> list[tuple[int, float]] | None:
    """Rerank documents via the reranker endpoint. Returns [(original_index, score)]."""
    if not documents:
        return []
    url = f"{RERANKER_URL}/v1/rerank"
    try:
        body = _post_json(
            url,
            {"model": RERANKER_MODEL, "query": query, "documents": documents, "top_n": top_n},
            RERANKER_TIMEOUT,
        )
    except Exception as exc:
        logger.debug("Reranker unavailable, skipping: %s", exc)
        return None
    results = body.get("results", [])
    if not isinstance(results, list):
        return None
    pairs: list[tuple[int, float]] = []
    for item in results:
        if isinstance(item, dict):
            idx = item.get("index")
            score = item.get("relevance_score", 0.0)
            if isinstance(idx, int):
                pairs.append((idx, float(score)))
    return sorted(pairs, key=lambda x: x[1], reverse=True)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _collect_files(root: Path, path_glob: str | None) -> list[Path]:
    """Collect indexable files under root, optionally filtered by glob."""
    files: list[Path] = []
    if path_glob:
        for p in root.glob(path_glob):
            if p.is_file() and p.suffix.lower() in CODE_EXTENSIONS:
                files.append(p)
        return sorted(files)[:MAX_FILES_TO_EMBED]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() in CODE_EXTENSIONS:
                files.append(p)
            if len(files) >= MAX_FILES_TO_EMBED:
                return sorted(files)
    return sorted(files)


def _read_preview(path: Path, limit: int = MAX_FILE_CHARS) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return None


def _keyword_boost(query: str, text: str) -> float:
    """Small bonus for exact keyword matches (0.0-0.05)."""
    terms = re.findall(r"[a-z0-9_]+", query.lower())
    text_lower = text.lower()
    hits = sum(1 for t in terms if t in text_lower and len(t) >= 3)
    return min(0.05, hits * 0.01)


@register_tool("nomic_search")
class NomicSearchTool(BaseTool):
    """Semantic code search using Nomic embeddings."""

    name = "nomic_search"
    schema = {
        "type": "function",
        "function": {
            "name": "nomic_search",
            "description": (
                "Search workspace files semantically using Nomic embeddings. "
                "Returns the most relevant code files and snippets for a natural language query. "
                "Use for finding code by meaning rather than exact text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query (e.g., 'function that handles user authentication')",
                    },
                    "path_glob": {
                        "type": "string",
                        "description": "Optional glob pattern to restrict search scope (e.g., '**/*.py', 'src/**/*.ts')",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 10)",
                    },
                },
                "required": ["query"],
            },
        },
    }

    def call(self, query: str, path_glob: str | None = None, top_k: int = TOP_K, **kwargs: Any) -> str:
        if not query or not query.strip():
            raise ToolError(self.name, "query is required")

        workspace = Path(WORKSPACE_ROOT).resolve()
        if not workspace.is_dir():
            raise ToolError(self.name, f"workspace not found: {workspace}")

        files = _collect_files(workspace, path_glob)
        if not files:
            return json.dumps({"results": [], "message": "No indexable files found"})

        # Read file contents for embedding.
        file_texts: list[str] = []
        file_paths: list[str] = []
        for f in files:
            preview = _read_preview(f)
            if preview and preview.strip():
                rel = str(f.relative_to(workspace))
                file_texts.append(f"# {rel}\n{preview}")
                file_paths.append(rel)

        if not file_texts:
            return json.dumps({"results": [], "message": "No readable files found"})

        # Try reranker first (simpler, doesn't require embedding the files).
        rerank_results = _rerank(query, file_texts, min(top_k, len(file_texts)))
        if rerank_results is not None:
            results = []
            for idx, score in rerank_results[:top_k]:
                if 0 <= idx < len(file_paths):
                    preview = file_texts[idx][:500]
                    results.append({
                        "file": file_paths[idx],
                        "score": round(score, 4),
                        "preview": preview,
                    })
            return json.dumps({"results": results, "method": "reranker"})

        # Fall back to embedding-based cosine similarity.
        all_texts = [query] + file_texts
        vectors = _embed(all_texts)
        if vectors is None:
            raise ToolError(
                self.name,
                f"Embedding service unavailable at {NOMIC_EMBED_URL}. "
                "Ensure llama-nomic is running on port 8083.",
            )

        query_vec = vectors[0]
        scored: list[tuple[int, float]] = []
        for i, fvec in enumerate(vectors[1:]):
            sim = _cosine_similarity(query_vec, fvec) + _keyword_boost(query, file_texts[i])
            scored.append((i, sim))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scored[:top_k]:
            preview = file_texts[idx][:500]
            results.append({
                "file": file_paths[idx],
                "score": round(score, 4),
                "preview": preview,
            })

        return json.dumps({"results": results, "method": "embedding"})
