"""
Function calling strategy abstraction.

Allows swapping between different function-calling formats:
- Nous (current AIUI standard)
- Qwen native (Qwen3.5-9B-BF16.gguf preferred format)
- DeepSeek compatible (for future compatibility)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import json
import re

TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.IGNORECASE | re.DOTALL)


def _normalize_call_dict(candidate: Any) -> Dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    name = str(candidate.get("name") or "").strip()
    if not name:
        return None
    arguments = candidate.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {}
    return {"name": name, "arguments": arguments}


class FunctionCallingStrategy(ABC):
    """Abstract base for function calling strategies."""

    name: str = None  # e.g., "nous", "qwen_native", "deepseek"

    @abstractmethod
    def build_tools_instruction(
        self, tools: List[str], system_message: Optional[str] = None
    ) -> str:
        """Build the instruction to inject into system prompt.
        
        Args:
            tools: List of tool names to enable
            system_message: Optional existing system message to append to
        
        Returns:
            str: Full instruction text for system message
        """
        pass

    @abstractmethod
    def parse_tool_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse tool calls from model response.
        
        Args:
            response_text: Raw model response text
        
        Returns:
            list: Parsed tool calls as [{"name": "...", "arguments": {...}}, ...]
        """
        pass


class NousFunctionCallingStrategy(FunctionCallingStrategy):
    """Nous format (current AIUI standard).
    
    Format:
        <tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>
    """

    name = "nous"

    def build_tools_instruction(
        self, tools: List[str], system_message: Optional[str] = None
    ) -> str:
        """Build Nous-format tool instruction."""
        # Get tool schemas from registry
        from .base import load_tools
        
        tool_instances = load_tools(tools)
        tool_specs = [t.schema for t in tool_instances]

        tools_section = json.dumps(tool_specs, indent=2)

        instruction = f"""You have access to the following tools:

{tools_section}

When you need to use a tool, output it in this format:
<tool_call>{{"name": "tool_name", "arguments": {{"arg1": "value1", "arg2": "value2"}}}}</tool_call>

You can use multiple tool calls in sequence if needed.
Always provide your final answer after tool execution.
"""
        
        if system_message:
            return f"{system_message}\n\n{instruction}"
        return instruction

    def parse_tool_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse Nous-format tool calls from response."""
        parsed_calls: List[Dict[str, Any]] = []
        for match in TOOL_CALL_BLOCK_RE.finditer(str(response_text or "")):
            try:
                call_dict = json.loads(match.group(1))
                normalized = _normalize_call_dict(call_dict)
                if normalized is not None:
                    parsed_calls.append(normalized)
            except json.JSONDecodeError:
                pass
        return parsed_calls


class QwenNativeFunctionCallingStrategy(FunctionCallingStrategy):
    """Qwen3.5-9B-BF16 native function calling format.
    
    Qwen natively outputs tool calls in structured format that llama.cpp
    can parse directly via built-in tool-call parsing.
    
    This strategy tells the model to use llama.cpp's native tool calling,
    which is more accurate and faster than Nous format.
    """

    name = "qwen_native"

    def build_tools_instruction(
        self, tools: List[str], system_message: Optional[str] = None
    ) -> str:
        """Build instruction for Qwen native function calling.
        
        When using llama.cpp with Qwen3.5, we enable --tools flag
        and let the model output native tool calls that llama.cpp parses.
        """
        from .base import load_tools
        
        tool_instances = load_tools(tools)
        tool_specs = [t.schema for t in tool_instances]

        # Qwen native: simply list the tools, model and llama.cpp handle the format
        tools_section = json.dumps(tool_specs, indent=2)

        instruction = f"""You have access to the following tools:

{tools_section}

Use these tools to help answer questions and complete tasks.
Use tool calls when appropriate, and provide your final answer.
"""
        
        if system_message:
            return f"{system_message}\n\n{instruction}"
        return instruction

    def parse_tool_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse Qwen native tool calls.
        
        Note: When using llama.cpp with --skip-chat-parsing disabled (default),
        llama.cpp extracts tool calls into a separate 'tool_calls' field in
        the JSON response. This parser handles text format for compatibility.
        """
        # Qwen native format is usually parsed upstream; this is a best-effort text fallback.
        patterns = [
            r'Tool Call:\s*(\{.*?\})(?:\n|$)',
            r'\[tool_call\]\s*(\{.*?\})\s*\[/tool_call\]',
        ]

        parsed_calls: List[Dict[str, Any]] = []
        # Reuse robust Nous parser first because Qwen often emits compatible blocks.
        parsed_calls.extend(NousFunctionCallingStrategy().parse_tool_calls(response_text))

        for pattern in patterns:
            matches = re.findall(pattern, str(response_text or ""), flags=re.DOTALL)
            for match in matches:
                try:
                    call_dict = json.loads(match)
                    normalized = _normalize_call_dict(call_dict)
                    if normalized is not None:
                        parsed_calls.append(normalized)
                except json.JSONDecodeError:
                    pass

        return parsed_calls


class DeepSeekFunctionCallingStrategy(FunctionCallingStrategy):
    """DeepSeek function calling format (for future compatibility).
    
    DeepSeek uses a different format than Nous. This strategy enables
    compatibility with DeepSeek API if switching models in future.
    """

    name = "deepseek"

    def build_tools_instruction(
        self, tools: List[str], system_message: Optional[str] = None
    ) -> str:
        """Build DeepSeek-format tool instruction."""
        from .base import load_tools
        
        tool_instances = load_tools(tools)
        tool_specs = [t.schema for t in tool_instances]

        tools_section = json.dumps(tool_specs, indent=2)

        instruction = f"""You have access to the following tools:

{tools_section}

When you want to use a tool, output it in this format:
<tool_use>
<invoke name="tool_name">
<parameter name="param1">value1</parameter>
<parameter name="param2">value2</parameter>
</invoke>
</tool_use>
"""
        
        if system_message:
            return f"{system_message}\n\n{instruction}"
        return instruction

    def parse_tool_calls(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse DeepSeek-format tool calls."""
        # DeepSeek format: <tool_use><invoke name="...">...<parameter>...</parameter></invoke></tool_use>
        pattern = r'<tool_use>\s*<invoke\s+name="([^"]+)">(.+?)</invoke>\s*</tool_use>'
        
        parsed_calls: List[Dict[str, Any]] = []
        matches = re.findall(pattern, str(response_text or ""), re.DOTALL)
        
        for tool_name, params_xml in matches:
            try:
                # Parse parameters from XML
                params_pattern = r'<parameter\s+name="([^"]+)">([^<]+)</parameter>'
                params_matches = re.findall(params_pattern, params_xml)
                
                arguments = {k: v for k, v in params_matches}
                normalized = _normalize_call_dict({"name": tool_name, "arguments": arguments})
                if normalized is not None:
                    parsed_calls.append(normalized)
            except Exception:
                # Skip malformed calls
                pass
        
        return parsed_calls


# Strategy registry
_strategies: Dict[str, FunctionCallingStrategy] = {}


def register_strategy(strategy: FunctionCallingStrategy) -> None:
    """Register a function calling strategy."""
    _strategies[strategy.name] = strategy


def get_strategy(name: str) -> FunctionCallingStrategy:
    """Get strategy by name."""
    if name not in _strategies:
        available = list(_strategies.keys())
        raise ValueError(
            f"Function calling strategy '{name}' not found. Available: {available}"
        )
    return _strategies[name]


def list_strategies() -> List[str]:
    """List available strategies."""
    return list(_strategies.keys())


# Register built-in strategies
register_strategy(NousFunctionCallingStrategy())
register_strategy(QwenNativeFunctionCallingStrategy())
register_strategy(DeepSeekFunctionCallingStrategy())
