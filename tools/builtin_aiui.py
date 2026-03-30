"""Existing AIUI tools, ported to deterministic registry pattern."""

import ast
import json
import operator
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .base import BaseTool, register_tool, ToolError


@register_tool("calculator")
class CalculatorTool(BaseTool):
    """Simple mathematical calculator."""
    
    name = "calculator"
    schema = {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Perform mathematical calculations. Supports +, -, *, /, %, ^, sqrt, sin, cos, tan, log, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g., '2+2*3', 'sqrt(16)', 'sin(3.14)')"
                    }
                },
                "required": ["expression"]
            }
        }
    }

    def call(self, expression: str, **kwargs) -> str:
        """Evaluate arithmetic expression with a strict AST allowlist."""
        allowed_ops: dict[type, object] = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        def _eval(node: ast.AST) -> float:
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return float(node.value)
            if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_ops:
                return float(allowed_ops[type(node.op)](_eval(node.operand)))
            if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
                left = _eval(node.left)
                right = _eval(node.right)
                return float(allowed_ops[type(node.op)](left, right))
            raise ValueError("Expression contains unsupported syntax")

        try:
            tree = ast.parse(expression, mode="eval")
            return str(_eval(tree))
        except ZeroDivisionError:
            raise ToolError(self.name, "Division by zero", "MATH_ERROR")
        except ValueError as e:
            raise ToolError(self.name, f"Invalid value: {e}", "MATH_ERROR")
        except Exception as e:
            raise ToolError(self.name, f"Calculation error: {e}", "CALC_ERROR")


@register_tool("get_current_time")
class GetCurrentTimeTool(BaseTool):
    """Get current date and time."""
    
    name = "get_current_time"
    schema = {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "description": "Optional time format string (Python strftime format)",
                        "default": "%Y-%m-%d %H:%M:%S"
                    },
                    "timezone": {
                        "type": "string",
                        "description": "Optional IANA timezone (e.g. UTC, America/New_York)",
                        "default": "UTC"
                    }
                },
                "required": []
            }
        }
    }

    def call(self, format: str = "%Y-%m-%d %H:%M:%S", timezone: str = "UTC", **kwargs) -> str:
        """Return current time in requested format."""
        try:
            tz_name = str(timezone or "UTC").strip() or "UTC"
            try:
                tz = ZoneInfo(tz_name)
            except ZoneInfoNotFoundError:
                tz_name = "UTC"
                tz = dt_timezone.utc
            return datetime.now(tz).strftime(format)
        except Exception as e:
            raise ToolError(self.name, f"Invalid format: {e}", "FORMAT_ERROR")


@register_tool("search_conversation")
class SearchConversationTool(BaseTool):
    """Search conversation history for relevant snippets."""
    
    name = "search_conversation"
    schema = {
        "type": "function",
        "function": {
            "name": "search_conversation",
            "description": "Search the conversation history for relevant information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to find in conversation history"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }

    def call(self, query: str, max_results: int = 5, **kwargs) -> str:
        """Search conversation history passed in through kwargs."""
        messages = kwargs.get("conversation_messages")
        if not isinstance(messages, list):
            return "{\"query\": \"\", \"matches\": [], \"count\": 0}"

        q = str(query or "").strip().lower()
        if not q:
            raise ToolError(self.name, "query is required", "VALIDATION_ERROR")

        max_results = max(1, min(10, int(max_results or 5)))
        terms = [term for term in q.split() if term]
        scored: list[tuple[int, dict[str, str]]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role") or "")
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            normalized = content.lower()
            score = sum(1 for term in terms if term in normalized)
            if score <= 0:
                continue
            snippet = content if len(content) <= 280 else f"{content[:279].rstrip()}..."
            scored.append((score, {"role": role, "snippet": snippet}))

        scored.sort(key=lambda item: item[0], reverse=True)
        payload = {
            "query": q,
            "matches": [item[1] for item in scored[:max_results]],
            "count": len(scored),
        }
        return json.dumps(payload, ensure_ascii=False)
