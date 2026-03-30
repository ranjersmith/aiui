"""
Base tool class and registry for AIUI.

Every tool must:
1. Inherit from BaseTool
2. Define its JSON schema
3. Implement call() with deterministic error handling
4. Register via @register_tool() decorator

This ensures atomic, composable, and model-queryable capabilities.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

# Global tool registry
TOOL_REGISTRY: Dict[str, "BaseTool"] = {}


class ToolError(Exception):
    """Raised when tool execution fails."""
    def __init__(self, name: str, message: str, code: str = "TOOL_ERROR"):
        self.name = name
        self.message = message
        self.code = code
        super().__init__(f"Tool '{name}' error [{code}]: {message}")


class BaseTool(ABC):
    """Abstract base for all tools in AIUI.
    
    Subclasses must implement:
    - schema: JSON Schema for input validation
    - call(): Execute tool with validated inputs
    """

    name: str = None  # Override in subclass
    schema: Dict[str, Any] = None  # Override in subclass with full JSON Schema

    def __init__(self):
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define 'name'")
        if not self.schema:
            raise ValueError(f"{self.__class__.__name__} must define 'schema'")
        self._validate_schema()

    def _validate_schema(self) -> None:
        """Ensure schema is valid for function calling."""
        required_keys = {"type", "function"}
        if not all(k in self.schema for k in required_keys):
            raise ValueError(
                f"Tool '{self.name}' schema must have keys: {required_keys}"
            )

        func = self.schema["function"]
        if "name" not in func:
            raise ValueError(
                f"Tool '{self.name}' schema['function'] must have 'name'"
            )
        if func["name"] != self.name:
            raise ValueError(
                f"Tool '{self.name}' schema name mismatch: "
                f"class.name='{self.name}' vs schema.function.name='{func['name']}'"
            )

    @abstractmethod
    def call(self, **kwargs) -> str:
        """Execute the tool.
        
        Args:
            **kwargs: Arguments matching schema['function']['parameters']
        
        Returns:
            str: Result as JSON string or plain text
        
        Raises:
            ToolError: If execution fails
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}'>"


def register_tool(name: str):
    """Decorator to register a tool in the global registry.
    
    Example:
        @register_tool("web_search")
        class WebSearchTool(BaseTool):
            schema = {...}
            def call(self, query: str, **kwargs) -> str:
                ...
    """
    def decorator(cls):
        if not issubclass(cls, BaseTool):
            raise TypeError(f"Tool class must inherit from BaseTool, got {cls}")
        
        instance = cls()
        if instance.name != name:
            raise ValueError(
                f"Tool registration name '{name}' doesn't match class name '{instance.name}'"
            )
        
        TOOL_REGISTRY[name] = instance
        logger.debug(f"Registered tool: {name}")
        return cls
    
    return decorator


def get_tool(name: str) -> Optional[BaseTool]:
    """Get registered tool by name."""
    return TOOL_REGISTRY.get(name)


def list_tools() -> Dict[str, BaseTool]:
    """Get all registered tools."""
    return dict(TOOL_REGISTRY)


def get_tool_schemas() -> list:
    """Get all tool schemas in OpenAI function calling format.
    
    Returns:
        list: Array of {"type": "function", "function": {...}} objects
              ready to pass to model as function_call
    """
    return [tool.schema for tool in TOOL_REGISTRY.values()]


def load_tools(tool_names: list) -> list:
    """Load specific tools by name.
    
    Args:
        tool_names: List of tool names to load (e.g., ["calculator", "web_search"])
    
    Returns:
        list: Tool instances in order requested
    
    Raises:
        ValueError: If tool name not found
    """
    tools = []
    for name in tool_names:
        tool = get_tool(name)
        if not tool:
            available = list(TOOL_REGISTRY.keys())
            raise ValueError(
                f"Tool '{name}' not found. Available: {available}"
            )
        tools.append(tool)
    return tools
