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
from . import builtin_llama  # noqa: F401
from . import builtin_aiui  # noqa: F401
from . import builtin_search  # noqa: F401
from . import builtin_catalog  # noqa: F401

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
