"""Resource catalog search tool.

Bridges AIUI's agent to the Qdrant-backed resource catalog at ~/.qwen/resources/.
Enables Qwen Code to discover available datasets, game resources, and other
indexed assets during coding sessions.
"""

from __future__ import annotations

import json
import logging
import sys
import os

from .base import BaseTool, register_tool, ToolError

logger = logging.getLogger(__name__)

# Lazy-load the catalog module
_catalog = None


def _get_catalog():
    global _catalog
    if _catalog is None:
        sys.path.insert(0, os.path.expanduser("~/.qwen/resources"))
        import catalog as _cat
        _catalog = _cat
    return _catalog


@register_tool("search_resources")
class SearchResourcesTool(BaseTool):
    """Search the resource catalog for available datasets and assets."""

    name = "search_resources"
    schema = {
        "type": "function",
        "function": {
            "name": "search_resources",
            "description": (
                "Search the resource catalog for available datasets, game resources, "
                "code examples, and other indexed assets. Uses semantic search with "
                "Nomic embeddings against the Qdrant vector database. "
                "Returns matching resources with descriptions, paths, tags, and metadata. "
                "Use this to discover what data and resources are available before "
                "starting a project."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural language search query describing what you're "
                            "looking for (e.g., 'maze game with ghosts', 'shooting "
                            "aliens', 'game with paddle and ball')"
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "default": 5,
                    },
                    "collection": {
                        "type": "string",
                        "description": (
                            "Filter by collection name (e.g., 'atari-gameplay'). "
                            "Leave empty to search all collections."
                        ),
                        "default": "",
                    },
                },
                "required": ["query"],
            },
        },
    }

    def call(self, query: str, max_results: int = 5, collection: str = "", **kwargs) -> str:
        try:
            catalog = _get_catalog()
        except Exception as e:
            raise ToolError(self.name, f"Catalog unavailable: {e}", "CATALOG_INIT_ERROR")

        try:
            results = catalog.search(
                query,
                limit=max_results,
                collection_name=collection,
                use_reranker=True,
            )
        except Exception as e:
            raise ToolError(self.name, f"Search failed: {e}", "SEARCH_ERROR")

        if not results:
            return json.dumps({"results": [], "message": "No matching resources found."})

        formatted = []
        for r in results:
            entry = {
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "path": r.get("path", ""),
                "collection": r.get("collection_name", ""),
                "type": r.get("resource_type", ""),
                "tags": r.get("tags", []),
            }
            if r.get("file_count"):
                entry["file_count"] = r["file_count"]
            if r.get("format_info"):
                fi = r["format_info"]
                if isinstance(fi, str):
                    try:
                        fi = json.loads(fi)
                    except (json.JSONDecodeError, TypeError):
                        pass
                entry["format_info"] = fi
            if r.get("score") is not None:
                entry["relevance_score"] = round(r["score"], 3)
            formatted.append(entry)

        return json.dumps({"results": formatted, "count": len(formatted)})
