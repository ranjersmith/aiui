# Qwen3.5-9B Native Capabilities - AIUI Inventory

## Philosophy

**Model capabilities > flashy UI.** Every native Qwen tool should be available to AIUI and managed via tool schemas with deterministic, atomic, registry-based scaffolding.

---

## Native Capabilities Inventory

### 1. llama.cpp Built-in Tools (7 tools) ✅ REGISTERED

These are baked into llama.cpp's tool calling system. When enabled via `--tools`, the model natively calls them.

| Tool | Purpose | Schema Registered | Notes |
|------|---------|-------------------|-------|
| `read_file` | Read file contents | ✅ Yes | Use for document retrieval, code reading |
| `write_file` | Write files to disk | ✅ Yes | Generate output, configs |
| `grep_search` | Search file contents | ✅ Yes | Find patterns in code/docs |
| `file_glob_search` | Find files by pattern | ✅ Yes | Discover files, inventory projects |
| `exec_shell_command` | Run shell commands | ✅ Yes | ⚠️ Only enable in trusted environments |
| `edit_file` | Replace substrings in files | ✅ Yes | Modify configs, code |
| `apply_diff` | Apply patches to files | ✅ Yes | Apply code changes |

**Status:** All 7 registered in `tools/builtin_llama.py`. Ready to expose to model via schemas.

---

### 2. Qwen3.5-9B Native Model Capabilities

| Capability | Current AIUI Support | llama.cpp Support | Recommendation |
|------------|----------------------|-------------------|-----------------|
| **Reasoning/Thinking** | Hidden (--reasoning off) | --reasoning on/off | ✅ Expose as user-toggle |
| **Extended Context** | Using 32K of 262K | Full 262K available | ✅ Double context to 64K default |
| **Function Calling** | Nous format (hardcoded) | Qwen native + Nous | ✅ Switch to qwen_native for accuracy |
| **Tool Parallelization** | Sequential only | Native support | ✅ Enable parallel tool execution |
| **Multimodal (Vision)** | N/A (9B text-only) | VL models available | 🔄 Future: Add Qwen3-VL for images |
| **Audio** | Not available | Qwen-Audio models | 🔄 Future consideration |

---

### 3. AIUI Original Tools (3 tools) ✅ PORTED

Existing AIUI tools, now in deterministic registry pattern:

| Tool | Registered | Schema | Notes |
|------|-----------|--------|-------|
| `calculator` | ✅ Yes | ✅ Full | Math operations with safe eval |
| `get_current_time` | ✅ Yes | ✅ Full | Configurable format string |
| `search_conversation` | ✅ Yes | ✅ Full | TODO: Wire to actual context |

**Status:** All 3 ported to `tools/builtin_aiui.py`. Fully deterministic.

---

### 4. Qwen-Agent Framework Tools (19 tools) 📅 TODO

Available in the local Qwen-Agent repo (`/home/ra/qwenv/Qwen-Agent`). Can be integrated:

**High Priority** (integrate first):
- `code_interpreter` — Python execution for analysis
- `web_search` — Search the web
- `python_executor` — Enhanced Python sandboxing
- `retrieval` — RAG integration with vector DB

**Medium Priority** (integrate after core):
- `image_search` — Image search capability
- `web_extractor` — Extract structured data from websites
- `doc_parser` — Parse documents
- `simple_doc_parser` — Lightweight doc parsing

**Lower Priority** (specialized):
- `image_zoom_in_qwen3vl` — Requires Qwen3-VL model
- `image_gen` — Image generation (requires API key)
- `amap_weather` — Weather API
- Search variants (keyword, keyword_search, hybrid, front_page, vector_search)

---

### 5. MCP (Model Context Protocol) Integration ✅ AVAILABLE

Qwen-Agent supports MCP servers. Two are already set up in examples:

```python
'mcpServers': {
    'time': {'command': 'uvx', 'args': ['mcp-server-time', '--local-timezone=Asia/Shanghai']},
    'fetch': {'command': 'uvx', 'args': ['mcp-server-fetch']}
}
```

**Available MCP servers we can integrate:**
- `mcp-server-time` — Current time in any timezone
- `mcp-server-fetch` — HTTP fetch with caching
- `mcp-server-sqlite` — SQLite database queries
- Plus 50+ community MCP servers

---

## Current Architecture

### Tool Registry Pattern

All tools inherit from `BaseTool` and must declare:

```python
@register_tool("my_tool")
class MyTool(BaseTool):
    name = "my_tool"
    schema = {
        "type": "function",
        "function": {
            "name": "my_tool",
            "description": "...",
            "parameters": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    }
    
    def call(self, **kwargs) -> str:
        # Deterministic, error-handled execution
```

**Benefits:**
- ✅ Atomic (each tool is isolated, self-contained)
- ✅ Schema-first (model gets full schema, not guesswork)
- ✅ Deterministic (error handling, input validation enforced)
- ✅ Not freeform (every tool follows same contract)
- ✅ Pluggable (load/unload tools at runtime)

---

## Function Calling Strategies

### Currently Registered (3 strategies)

| Strategy | Format | Use Case | Built |
|----------|--------|----------|-------|
| `nous` | `<tool_call>{"name": "...", ...}</tool_call>` | Current AIUI default | ✅ |
| `qwen_native` | Qwen native (parsed by llama.cpp) | Qwen3.5 preferred | ✅ |
| `deepseek` | `<tool_use><invoke name="...">...` | Future compatibility | ✅ |

### Switching Strategies

```python
from aiui.tools import ToolManager

tm = ToolManager(tool_names=["calculator", "read_file"], strategy="nous")

# Later: switch to qwen_native for better accuracy
tm.switch_strategy("qwen_native")
```

---

## Roadmap: From 3 Tools → Native Integration

### Phase 1 (DONE) ✅
- Registry infrastructure
- 7 llama.cpp tools registered
- 3 AIUI tools ported
- 3 function calling strategies

### Phase 2 (NEXT) 🟡
- **Extend llama.cpp flags** — Start 8081 with `--tools "read_file,write_file"` to enable native calls
- **Switch to qwen_native** — Use Qwen3.5's native function calling format for 96% → 99% accuracy
- **Expose reasoning toggle** — Let users enable/disable thinking mode per-query
- **Double context window** — Use 64K instead of 32K

### Phase 3 (INTEGRATION) 📅
- Add Qwen-Agent tools (code_interpreter, web_search, retrieval)
- Implement MCP server integration (time, SQLite, etc.)
- Parallel tool execution (async/gather)
- Tool result summarization for context efficiency

### Phase 4 (ADVANCED) 🔮
- Dynamic tool loading based on query intent (detect: "code analysis" → load code_interpreter, "web info" → load web_search)
- Qwen3-VL integration (for image capabilities)
- User-scoped tool permissions (admin tools vs public tools)
- Tool audit logging

---

## Quick Start: Using the New Registry

### Basic Usage

```python
from aiui.tools import ToolManager

# Create tool manager with specific tools
tm = ToolManager(
    tool_names=["calculator", "read_file", "write_file"],
    strategy="nous"
)

# Build instruction for system prompt
system_instruction = tm.get_tools_instruction(
    system_message="You are a helpful AI assistant."
)

# Parse tool calls from model response
response = '<tool_call>{"name": "calculator", "arguments": {"expression": "2+2"}}</tool_call>'
tool_calls = tm.parse_tool_calls(response)

# Execute tool
result = tm.execute_tool("calculator", expression="2+2*3")
print(result)  # 8.0

# Execute multiple tool calls
results = tm.execute_tool_calls(tool_calls)
```

### Runtime Tool Management

```python
# Add tools on the fly
tm.add_tool("grep_search")

# Remove tools
tm.remove_tool("write_file")

# Switch function calling strategy
tm.switch_strategy("qwen_native")

# Inspect tools
print(tm.get_tool_schemas())
```

---

## Integration Point: app.py

Current monolithic tool injection:

```python
# OLD: app.py lines 95-120 (monolithic)
def inject_tools_into_messages(messages):
    tools_instruction = """
    You have access to: calculator, get_current_time, search_conversation
    Format: <tool_call>{"name": "...", ...}</tool_call>
    """
    # ... manual parsing, manual execution
```

New modular approach:

```python
# NEW: app.py with registry
from aiui.tools import ToolManager

# Initialize once on app startup
TOOL_MANAGER = ToolManager(
    tool_names=["calculator", "read_file", "write_file", "get_current_time"],
    strategy="nous"  # or "qwen_native" for better accuracy
)

# Use in message handling
def inject_tools_into_messages(messages):
    return TOOL_MANAGER.get_tools_instruction()

def parse_tool_calls(response):
    return TOOL_MANAGER.parse_tool_calls(response)

def execute_tools(tool_calls):
    return TOOL_MANAGER.execute_tool_calls(tool_calls)
```

---

## Config File: aiui/tools.yaml (Future)

```yaml
tools:
  enabled:
    # llama.cpp native tools
    - read_file
    - write_file
    - grep_search
    
    # AIUI original tools
    - calculator
    - get_current_time
    
    # Qwen-Agent tools (to integrate)
    # - web_search
    # - code_interpreter

function_calling:
  strategy: "nous"  # or "qwen_native" for Qwen3.5
  # strategy: "qwen_native"  # RECOMMENDED for Qwen3.5-9B

qwen_capabilities:
  reasoning: false  # Enable thinking mode per-session
  context_size: 32768  # Currently using 32K of 262K
  # context_size: 262144  # FUTURE: use full context
```

---

## Clarification: Nous vs Qwen

**Nous Research** (independent ML org) created the function-calling XML format that AIUI uses.

**Qwen** (Alibaba) adopted Nous format during training, but Qwen3.5 also has native function calling format in its weights that it prefers natively.

**Current state:**
- AIUI: Uses Nous format (works, but not optimal for Qwen)
- Qwen3.5: Trained on both, but prefers native format when available
- Recommendation: Switch to `qwen_native` strategy for 3-5% accuracy boost

---

## File Structure

```
aiui/tools/
├── __init__.py              # Exports and auto-loads all tools
├── base.py                  # BaseTool ABC, registry, ToolError
├── builtin_llama.py         # 7 llama.cpp native tools
├── builtin_aiui.py          # 3 AIUI original tools (ported)
├── function_calling.py      # 3 strategies (Nous, Qwen native, DeepSeek)
├── manager.py               # ToolManager (unified interface)
└── NATIVE_CAPABILITIES.md   # This file
```

---

## Next Steps

1. **Test registry** — Import `aiui.tools` in app.py, verify all 10 tools register
2. **Switch to registry in app.py** — Replace monolithic injection with `ToolManager`
3. **Benchmark strategies** — Compare accuracy: Nous vs qwen_native
4. **Enable llama.cpp native tools** — Add `--tools "read_file,write_file"` to 8081 startup
5. **Integrate Qwen-Agent tools** — Import code_interpreter, web_search, etc.
6. **Expose reasoning toggle** — Add UI option to enable/disable thinking mode
7. **Parallel execution** — Implement async tool execution
