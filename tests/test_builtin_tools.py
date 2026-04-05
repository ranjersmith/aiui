"""Tests for individual tool execution (builtin_aiui tools)."""

import json

import pytest
from tools.base import ToolError, get_tool


class TestCalculatorTool:
    def setup_method(self):
        self.tool = get_tool("calculator")

    # --- arithmetic happy paths ---

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

    def test_floor_division(self):
        assert json.loads(self.tool.call(expression="7//2")) == 3.0

    def test_modulo(self):
        assert json.loads(self.tool.call(expression="10%3")) == 1.0

    def test_unary_negative(self):
        assert json.loads(self.tool.call(expression="-5+3")) == -2.0

    def test_unary_positive(self):
        assert json.loads(self.tool.call(expression="+5")) == 5.0

    def test_float_literals(self):
        assert json.loads(self.tool.call(expression="1.5+2.5")) == 4.0

    def test_deeply_nested_parens(self):
        assert json.loads(self.tool.call(expression="((((1+2))))")) == 3.0

    # --- error handling ---

    def test_division_by_zero(self):
        with pytest.raises(ToolError, match="Division by zero"):
            self.tool.call(expression="1/0")

    def test_empty_expression(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="")

    # --- security: AST allowlist rejects dangerous input ---

    def test_rejects_function_call(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="__import__('os').system('id')")

    def test_rejects_attribute_access(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="().__class__.__bases__")

    def test_rejects_name_lookup(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="open")

    def test_rejects_list_literal(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="[1,2,3]")

    def test_rejects_string_literal(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="'hello'")

    def test_rejects_lambda(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="lambda: 1")

    def test_rejects_walrus(self):
        with pytest.raises(ToolError):
            self.tool.call(expression="(x:=1)")


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
