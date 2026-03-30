"""
Tool initialization and loading.

Import this module to auto-register all tools.
"""

from .base import (
    BaseTool,
    ToolError,
    register_tool,
    get_tool,
    list_tools,
    load_tools,
    get_tool_schemas,
    TOOL_REGISTRY,
)
from .manager import ToolManager
from .function_calling import get_strategy, list_strategies


# Import all tool modules to trigger @register_tool() decorators
from . import builtin_llama
from . import builtin_aiui

__all__ = [
    "BaseTool",
    "ToolError",
    "register_tool",
    "get_tool",
    "list_tools",
    "load_tools",
    "get_tool_schemas",
    "TOOL_REGISTRY",
    "ToolManager",
    "get_strategy",
    "list_strategies",
]
