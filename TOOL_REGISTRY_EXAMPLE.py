"""
Example: Integrating ToolManager into AIUI's app.py

This shows the minimal changes needed to use the new registry system.
"""

# ============================================================================
# OLD APPROACH (app.py lines 95-120, monolithic, hardcoded)
# ============================================================================

# TOOL_CALL_BLOCK_RE = regex with one hardcoded pattern
# build_agent_tool_specs() returns manually crafted [3 tools]
# inject_tools_into_messages() constructs instruction manually
# parse_assistant_tool_calls() regex on response
# Every change = edit multiple functions


# ============================================================================
# NEW APPROACH (modular, schema-first, atomic)
# ============================================================================

from flask import Flask, request, jsonify
from aiui.tools import ToolManager

app = Flask(__name__)

# Initialize tool manager once at app startup
# This loads all registered tools and sets up function calling strategy
TOOL_MANAGER = ToolManager(
    tool_names=[
        # AIUI original tools
        "calculator",
        "get_current_time",
        "search_conversation",
        
        # llama.cpp native tools (expand as needed)
        "read_file",
        "write_file",
        "grep_search",
        # "exec_shell_command",  # Uncomment only in trusted environments
        # "edit_file",
        # "apply_diff",
    ],
    strategy="nous"  # Can switch to "qwen_native" for better accuracy with Qwen3.5
)

# Store in global for use in message handling
app.tool_manager = TOOL_MANAGER


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    """Handle chat completion requests with integrated tool calling."""
    data = request.json
    messages = data.get("messages", [])
    
    # Inject tools into system message
    if messages and messages[0].get("role") == "system":
        # Append tools instruction to existing system message
        system_msg = messages[0].get("content", "")
        messages[0]["content"] = app.tool_manager.get_tools_instruction(system_msg)
    else:
        # Prepend new system message with tools
        messages.insert(0, {
            "role": "system",
            "content": app.tool_manager.get_tools_instruction()
        })
    
    # Call LLM
    response = call_llm(messages, **data)
    
    # Parse tool calls from response
    tool_calls = app.tool_manager.parse_tool_calls(response)
    
    if tool_calls:
        # Execute tools (this example does sequential execution)
        tool_results = app.tool_manager.execute_tool_calls(tool_calls)
        
        # Optionally: Continue conversation with tool results
        # For now, return both response and tool results
        return jsonify({
            "response": response,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "model": data.get("model", "Qwen3.5-9B-BF16.gguf"),
        })
    
    return jsonify({
        "response": response,
        "model": data.get("model", "Qwen3.5-9B-BF16.gguf"),
    })


# ============================================================================
# MAJOR ADVANTAGES
# ============================================================================

"""
1. ADD NEW TOOL:
   OLD: Edit app.py to add to hardcoded list, regex, injection, parsing
   NEW: Create tools/builtin/my_tool.py with @register_tool("my_tool")
        Done. No app.py changes.

2. SCHEMAS:
   OLD: Tools not in schema, model guesses format
   NEW: Every tool declares full JSON schema, model gets it

3. DETERMINISM:
   OLD: Tool can fail silently, hardcoded error handling
   NEW: BaseTool enforces error handling via ToolError

4. FLEXIBILITY:
   OLD: Nous format hardcoded forever
   NEW: tm.switch_strategy("qwen_native") at runtime

5. TESTING:
   OLD: Test tool calling in integrated test within app
   NEW: Test tools independently: from tools import get_tool; tool = get_tool("calculator"); tool.call(expression="2+2")

6. QWEN CAPABILITIES:
   OLD: Hidden (3 tools max)
   NEW: 10+ atomic tools available, easily expandable to 20+
"""


# ============================================================================
# MIGRATION STRATEGY (Do NOT break existing app while refactoring)
# ============================================================================

"""
STEP 1 (Parallel):
  - App.py runs with OLD monolithic tool system
  - Alongside it, ToolManager works independently
  - New code uses ToolManager, old code uses old system
  
STEP 2 (Switchover):
  - Once ToolManager handles all use cases
  - Replace old inject_tools() to use tm.get_tools_instruction()
  - Replace old parse_tool_calls() to use tm.parse_tool_calls()
  - Keep tool execution logic similar initially
  
STEP 3 (Enhance):
  - Add new tools from llama.cpp (grep_search, read_file, etc.)
  - Benchmark: Nous vs qwen_native strategies
  - Parallel tool execution (async/gather)
"""
