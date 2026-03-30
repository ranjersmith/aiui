from __future__ import annotations

from typing import Any

from tools.base import ToolError
from tools.manager import ToolManager


class _DummyManager(ToolManager):
    def __init__(self) -> None:
        self.tool_names = ["calculator"]
        self.tools = []
        self.strategy = None
        self.strategy_name = "test"

    def execute_tool(self, tool_name: str, **kwargs: Any) -> str:
        if kwargs.get("boom"):
            raise ToolError(tool_name, "failed")
        return f"ok:{kwargs.get('expression', '')}"


def test_execute_tool_calls_preserves_duplicate_names() -> None:
    manager = _DummyManager()

    result = manager.execute_tool_calls(
        [
            {"name": "calculator", "arguments": {"expression": "1+1"}},
            {"name": "calculator", "arguments": {"expression": "2+2"}},
        ]
    )

    assert result["calculator"] == "ok:1+1"
    assert result["calculator#2"] == "ok:2+2"


def test_execute_tool_calls_keeps_error_per_occurrence() -> None:
    manager = _DummyManager()

    result = manager.execute_tool_calls(
        [
            {"name": "calculator", "arguments": {"boom": True}},
            {"name": "calculator", "arguments": {"boom": True}},
        ]
    )

    assert result["calculator"].startswith("Error:")
    assert result["calculator#2"].startswith("Error:")
