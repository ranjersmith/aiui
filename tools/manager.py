"""
Tool manager - integrates registry and function calling strategies.

Example usage:

    from aiui.tools import ToolManager
    
    # Initialize with specific tools and function calling strategy
    tm = ToolManager(
        tool_names=["calculator", "read_file", "write_file"],
        strategy="nous"
    )
    
    # Get tools instruction for system prompt
    system_msg = "You are a helpful assistant."
    tools_instruction = tm.get_tools_instruction(system_msg)
    
    # Parse tool calls from response
    response = "<tool_call>{"name": "calculator", "arguments": {"expression": "2+2"}}</tool_call>"
    tool_calls = tm.parse_tool_calls(response)
    
    # Execute a tool
    result = tm.execute_tool("calculator", expression="2+2")
"""

from typing import List, Dict, Any, Optional
import json

from .base import load_tools, get_tool_schemas, ToolError
from .function_calling import get_strategy, list_strategies


class ToolManager:
    """Manages tools and function calling strategy."""

    def __init__(
        self,
        tool_names: Optional[List[str]] = None,
        strategy: str = "nous"
    ):
        """Initialize tool manager.
        
        Args:
            tool_names: List of tools to enable. If None, all available tools.
            strategy: Function calling strategy ("nous", "qwen_native", "deepseek")
        """
        if tool_names:
            self.tools = load_tools(tool_names)
            self.tool_names = tool_names
        else:
            from .base import list_tools
            tool_dict = list_tools()
            self.tools = list(tool_dict.values())
            self.tool_names = list(tool_dict.keys())
        
        self.strategy = get_strategy(strategy)
        self.strategy_name = strategy

    def get_tools_instruction(self, system_message: Optional[str] = None) -> str:
        """Get formatted tools instruction for system prompt.
        
        Args:
            system_message: Optional existing system message to append to
        
        Returns:
            str: Full instruction text including tool definitions
        """
        return self.strategy.build_tools_instruction(self.tool_names, system_message)

    def parse_tool_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse tool calls from model response.
        
        Args:
            response_text: Raw model response text
        
        Returns:
            list: Parsed tool calls as [{"name": "...", "arguments": {...}}, ...]
        """
        return self.strategy.parse_tool_calls(response_text)

    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """Execute a tool.
        
        Args:
            tool_name: Name of tool to execute
            **kwargs: Arguments for the tool
        
        Returns:
            str: Tool execution result
        
        Raises:
            ToolError: If execution fails
        """
        from .base import get_tool
        
        tool = get_tool(tool_name)
        if not tool:
            raise ToolError(
                "ToolManager",
                f"Tool '{tool_name}' not found",
                "NOT_FOUND"
            )
        
        return tool.call(**kwargs)

    def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute multiple tool calls.
        
        Args:
            tool_calls: List of tool calls as [{"name": "...", "arguments": {...}}, ...]
        
        Returns:
            dict: Results keyed by tool name: {"tool_name": "result", ...}
        """
        results = {}
        for call in tool_calls:
            tool_name = call.get("name")
            arguments = call.get("arguments", {})
            
            try:
                result = self.execute_tool(tool_name, **arguments)
                results[tool_name] = result
            except ToolError as e:
                results[tool_name] = f"Error: {e.message}"
        
        return results

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get all tool schemas in OpenAI function calling format."""
        return [t.schema for t in self.tools]

    def switch_strategy(self, strategy: str) -> None:
        """Switch to a different function calling strategy."""
        self.strategy = get_strategy(strategy)
        self.strategy_name = strategy

    def add_tool(self, tool_name: str) -> None:
        """Add a tool at runtime."""
        from .base import get_tool
        
        tool = get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not registered")
        
        if tool_name not in self.tool_names:
            self.tool_names.append(tool_name)
            self.tools.append(tool)

    def remove_tool(self, tool_name: str) -> None:
        """Remove a tool at runtime."""
        if tool_name in self.tool_names:
            idx = self.tool_names.index(tool_name)
            self.tool_names.remove(tool_name)
            del self.tools[idx]

    def __repr__(self) -> str:
        return (
            f"<ToolManager tools={self.tool_names} "
            f"strategy={self.strategy_name}>"
        )
