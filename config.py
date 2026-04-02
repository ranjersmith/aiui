"""AIUI configuration — env helpers and all runtime constants."""

from __future__ import annotations

import os
import re
from tools import list_strategies


def env_bool(key: str, default: bool = False) -> bool:
    """Parse env var as boolean: '1', 'true', 'yes' → True; '0', 'false', 'no' → False; unset/empty → default."""
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    """Parse env var as int with fallback."""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def env_float(key: str, default: float) -> float:
    """Parse env var as float with fallback."""
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


# ── Core settings ──────────────────────────────────────────────────────────
LLM_BASE_URL = os.getenv("AIUI_LLM_BASE_URL", "http://host.docker.internal:8081").rstrip("/")
DEFAULT_MODEL = os.getenv("AIUI_DEFAULT_MODEL", os.getenv("CHAT_MODEL", "Qwen3-Coder-30B-A3B-Instruct-Q5_K_M.gguf"))
REQUEST_TIMEOUT_SECONDS = int(os.getenv("AIUI_REQUEST_TIMEOUT_SECONDS", "120"))
SYSTEM_PROMPT = os.getenv("AIUI_SYSTEM_PROMPT", "You are a concise, helpful assistant.").strip()

# CANONICAL MATH DELIMITER CONTRACT: See MATH_DELIMITERS_CONTRACT.json for the contract.
# Backend guidance: Use $...$ for inline math, $$...$$ for display math (KaTeX-compatible).
RESPONSE_FORMAT_GUIDANCE = (
    "Response format requirements:\n"
    "- Return valid Markdown.\n"
    "- Use $...$ for inline math. Use $$...$$ for display math.\n"
    "- Every math delimiter must be balanced and closed.\n"
    "- Before finishing, verify there are no unmatched $ or $$.\n"
    "- Do not place LaTeX outside math delimiters.\n"
    "- Do not wrap equations in bold or italics.\n"
    "- Leave a blank line before and after headings, lists, and display equations.\n"
    "- Keep lists valid and consistently indented.\n"
    "- Do not emit truncated or unfinished sentences.\n"
    "- Close all formatting markers: **, _, and code fences."
)
DEFAULT_API_KEY = os.getenv("AIUI_OPENAI_API_KEY", "").strip()
UPSTREAM_HEALTH_TIMEOUT_SECONDS = env_float("AIUI_UPSTREAM_HEALTH_TIMEOUT_SECONDS", 8.0)
CONTEXT_BUDGET_TOKENS = env_int("AIUI_CONTEXT_BUDGET_TOKENS", 4096)
CONTEXT_REPLY_RESERVE_TOKENS = env_int("AIUI_CONTEXT_REPLY_RESERVE_TOKENS", 1024)
MODULE_CATALOG_CACHE_TTL_SECONDS = env_float("AIUI_MODULE_CATALOG_CACHE_TTL_SECONDS", 60.0)

# ── Agent settings ─────────────────────────────────────────────────────────
AGENT_MAX_LLM_CALLS_PER_RUN = env_int("AIUI_AGENT_MAX_LLM_CALLS_PER_RUN", 6)
AGENT_MAX_TOOL_CALLS_PER_TURN = env_int("AIUI_AGENT_MAX_TOOL_CALLS_PER_TURN", 4)
AGENT_ENABLE_NON_STREAM_LOOP = env_bool("AIUI_AGENT_ENABLE_NON_STREAM_LOOP", True)
AGENT_ENABLE_STREAM_LOOP = env_bool("AIUI_AGENT_ENABLE_STREAM_LOOP", True)
AGENT_TOOL_PROFILE = os.getenv("AIUI_AGENT_TOOL_PROFILE", "safe").strip().lower() or "safe"
AGENT_TOOL_STRATEGY = os.getenv("AIUI_AGENT_TOOL_STRATEGY", "nous").strip().lower() or "nous"
AGENT_ENABLED_TOOLS_RAW = os.getenv("AIUI_AGENT_ENABLED_TOOLS", "").strip()

# SECURITY: Disable doc/ppt external extractors by default to avoid unexpected process spawning.
# Set AIUI_ENABLE_EXTERNAL_EXTRACTORS=1 to enable catppt, catdoc, antiword extraction.
ENABLE_EXTERNAL_EXTRACTORS = env_bool("AIUI_ENABLE_EXTERNAL_EXTRACTORS", False)

# ── Attachment / document limits ───────────────────────────────────────────
MAX_ATTACHMENTS = env_int("AIUI_MAX_ATTACHMENTS", env_int("AIUI_MAX_IMAGE_ATTACHMENTS", 4))
MAX_ATTACHMENT_DATA_URL_CHARS = env_int(
    "AIUI_MAX_ATTACHMENT_DATA_URL_CHARS", env_int("AIUI_MAX_IMAGE_DATA_URL_CHARS", 8000000)
)
MAX_DOCUMENT_BYTES = env_int("AIUI_MAX_DOCUMENT_BYTES", 12000000)
MAX_DOCUMENT_TEXT_CHARS = env_int("AIUI_MAX_DOCUMENT_TEXT_CHARS", 16000)
MAX_TOTAL_DOCUMENT_TEXT_CHARS = env_int("AIUI_MAX_TOTAL_DOCUMENT_TEXT_CHARS", 48000)
IMAGE_PART_TOKEN_ESTIMATE = env_int("AIUI_IMAGE_PART_TOKEN_ESTIMATE", 768)

# ── Regexes ────────────────────────────────────────────────────────────────
PARKER_EVIDENCE_LABEL_RE = re.compile(r"\[E\d+\]")
PARKER_EVIDENCE_BULLET_RE = re.compile(r"(?mi)^\s*-\s*\[E\d+\]\s+")
# Also defined in tools/function_calling.py (kept separate to avoid circular imports).
TOOL_CALL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.IGNORECASE | re.DOTALL)
THINK_BLOCK_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.IGNORECASE)

# ── Rate limiting ──────────────────────────────────────────────────────────
_REQUEST_TIMESTAMPS: list[float] = []
_MAX_REQUESTS_PER_SECOND = int(os.getenv("AIUI_MAX_REQUESTS_PER_SECOND", "10"))
_MAX_ATTACHMENT_BYTES_PER_REQUEST = int(os.getenv("AIUI_MAX_ATTACHMENT_BYTES_PER_REQUEST", "25000000"))

# ── Module catalog cache ───────────────────────────────────────────────────
_MODULE_CATALOG_CACHE: dict[str, object] = {"expires_at": 0.0, "body": None}

# ── Tool profiles ──────────────────────────────────────────────────────────
DEFAULT_AGENT_TOOL_NAMES = [
    "get_current_time",
    "calculator",
    "search_conversation",
    "read_file",
    "write_file",
    "grep_search",
    "file_glob_search",
    "exec_shell_command",
    "edit_file",
    "apply_diff",
]
SAFE_AGENT_TOOL_NAMES = [
    "get_current_time",
    "calculator",
    "search_conversation",
    "read_file",
    "grep_search",
    "file_glob_search",
    "nomic_search",
]
MINIMAL_AGENT_TOOL_NAMES = [
    "get_current_time",
    "calculator",
    "search_conversation",
]
AGENT_TOOL_PROFILES: dict[str, list[str] | None] = {
    "safe": SAFE_AGENT_TOOL_NAMES,
    "minimal": MINIMAL_AGENT_TOOL_NAMES,
    "trusted": None,
    "all": None,
}
AGENT_ALLOWED_STRATEGIES = set(list_strategies())

# ── Document type sets ─────────────────────────────────────────────────────
TEXT_DOCUMENT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".py",
    ".log",
}
WORDPROCESSINGML_NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DRAWINGML_TEXT_TAG = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"

# ── Tool sandboxing ───────────────────────────────────────────────────────
# WORKSPACE_ROOT restricts file tools (read_file, write_file, edit_file,
# apply_diff, grep_search, file_glob_search) to this directory tree.
# Set to empty string to disable sandboxing (legacy behaviour).
WORKSPACE_ROOT = os.getenv("AIUI_WORKSPACE_ROOT", os.path.expanduser("~")).rstrip("/")

# SHELL_COMMAND_ALLOWLIST restricts exec_shell_command to these executables.
# Comma-separated. Empty = allow all (legacy behaviour — use with trusted profiles only).
_SHELL_ALLOWLIST_RAW = os.getenv("AIUI_SHELL_COMMAND_ALLOWLIST", "").strip()
SHELL_COMMAND_ALLOWLIST: set[str] | None = (
    {cmd.strip() for cmd in _SHELL_ALLOWLIST_RAW.split(",") if cmd.strip()}
    if _SHELL_ALLOWLIST_RAW
    else None
)
