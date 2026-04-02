"""Tests for individual tool execution (builtin_aiui tools)."""

import json
from tools.base import get_tool


class TestCalculatorTool:
    def setup_method(self):
        self.tool = get_tool("calculator")

    def test_basic_addition(self):
        result = json.loads(self.tool.call(expression="2+3"))
        assert result == 5.0

    def test_multiplication(self):
        result = json.loads(self.tool.call(expression="7*8"))
        assert result == 56.0

    def test_division(self):
        result = json.loads(self.tool.call(expression="10/4"))
        assert result == 2.5

    def test_nested_expression(self):
        result = json.loads(self.tool.call(expression="(2+3)*4"))
        assert result == 20.0

    def test_power(self):
        result = json.loads(self.tool.call(expression="2**10"))
        assert result == 1024.0


class TestGetCurrentTimeTool:
    def setup_method(self):
        self.tool = get_tool("get_current_time")

    def test_returns_datetime_string(self):
        result = self.tool.call()
        # Should be a recognizable datetime string
        assert len(result) >= 10
        assert "-" in result  # date separator

    def test_with_timezone(self):
        result = self.tool.call(timezone="US/Eastern")
        assert len(result) >= 10

    def test_invalid_timezone_returns_error(self):
        result = self.tool.call(timezone="Fake/Place")
        assert "error" in result.lower() or "unknown" in result.lower() or len(result) >= 10


class TestSearchConversationTool:
    def setup_method(self):
        self.tool = get_tool("search_conversation")

    def test_finds_matching_message(self):
        messages = [
            {"role": "user", "content": "Tell me about quantum computing"},
            {"role": "assistant", "content": "Quantum computing uses qubits"},
            {"role": "user", "content": "What about classical computers?"},
        ]
        result = json.loads(self.tool.call(
            query="quantum",
            conversation_messages=messages,
        ))
        assert result["count"] > 0
        texts = [m["snippet"] for m in result["matches"]]
        assert any("quantum" in t.lower() for t in texts)

    def test_no_matches(self):
        messages = [{"role": "user", "content": "Hello world"}]
        result = json.loads(self.tool.call(
            query="xyznonexistent",
            conversation_messages=messages,
        ))
        assert result["count"] == 0
