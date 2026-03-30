"""
Native llama.cpp tools - deterministically scaffolded.

These tools are built into llama.cpp's tool calling system.
When the model calls these, llama.cpp will execute them.
We scaffold them here for AIUI to expose their schemas to the model.
"""

import json
import subprocess
import os
from pathlib import Path
from typing import Optional

from .base import BaseTool, register_tool, ToolError


@register_tool("read_file")
class ReadFileTool(BaseTool):
    """Read file contents from disk."""
    
    name = "read_file"
    schema = {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to read"
                    }
                },
                "required": ["file_path"]
            }
        }
    }

    def call(self, file_path: str, **kwargs) -> str:
        """Read file - note: llama.cpp will execute this natively."""
        try:
            file_path = Path(file_path).expanduser()
            if not file_path.exists():
                raise ToolError(self.name, f"File not found: {file_path}")
            if not file_path.is_file():
                raise ToolError(self.name, f"Path is not a file: {file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return content
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(self.name, str(e), "READ_ERROR")


@register_tool("write_file")
class WriteFileTool(BaseTool):
    """Write content to a file."""
    
    name = "write_file"
    schema = {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates file if it doesn't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file to write"
                    },
                    "contents": {
                        "type": "string",
                        "description": "Content to write to the file"
                    }
                },
                "required": ["file_path", "contents"]
            }
        }
    }

    def call(self, file_path: str, contents: str, **kwargs) -> str:
        """Write file - note: llama.cpp will execute this natively."""
        try:
            file_path = Path(file_path).expanduser()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(contents)
            
            return f"Successfully wrote {len(contents)} bytes to {file_path}"
        except Exception as e:
            raise ToolError(self.name, str(e), "WRITE_ERROR")


@register_tool("grep_search")
class GrepSearchTool(BaseTool):
    """Search file contents using grep-like pattern matching."""
    
    name = "grep_search"
    schema = {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Search files for matching patterns (grep-like functionality).",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Pattern to search for (supports regex)"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 20
                    }
                },
                "required": ["pattern", "path"]
            }
        }
    }

    def call(self, pattern: str, path: str, max_results: int = 20, **kwargs) -> str:
        """Search files using grep."""
        try:
            path = Path(path).expanduser()
            if not path.exists():
                raise ToolError(self.name, f"Path not found: {path}")
            
            cmd = ["grep", "-r", "-n", pattern]
            if path.is_file():
                cmd.append(str(path))
            else:
                cmd.extend([str(path)])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            lines = result.stdout.strip().split('\n')[:max_results]
            return '\n'.join(lines)
        except subprocess.TimeoutExpired:
            raise ToolError(self.name, "Search timed out", "TIMEOUT")
        except Exception as e:
            raise ToolError(self.name, str(e), "GREP_ERROR")


@register_tool("file_glob_search")
class FileGlobSearchTool(BaseTool):
    """Find files matching a glob pattern."""
    
    name = "file_glob_search"
    schema = {
        "type": "function",
        "function": {
            "name": "file_glob_search",
            "description": "Find files matching a glob pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match (e.g., '**/*.py')"
                    },
                    "root_path": {
                        "type": "string",
                        "description": "Root directory to search from",
                        "default": "."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of files to return",
                        "default": 50
                    }
                },
                "required": ["pattern"]
            }
        }
    }

    def call(self, pattern: str, root_path: str = ".", max_results: int = 50, **kwargs) -> str:
        """Search for files matching glob pattern."""
        try:
            root = Path(root_path).expanduser()
            if not root.exists():
                raise ToolError(self.name, f"Root path not found: {root}")
            
            matches = list(root.glob(pattern))[:max_results]
            
            return '\n'.join(str(m) for m in matches)
        except Exception as e:
            raise ToolError(self.name, str(e), "GLOB_ERROR")


@register_tool("exec_shell_command")
class ExecShellCommandTool(BaseTool):
    """Execute shell commands."""
    
    name = "exec_shell_command"
    schema = {
        "type": "function",
        "function": {
            "name": "exec_shell_command",
            "description": "Execute a shell command and return output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds",
                        "default": 30
                    }
                },
                "required": ["command"]
            }
        }
    }

    def call(self, command: str, timeout: int = 30, **kwargs) -> str:
        """Execute shell command - CAUTION: Only enable in trusted environments."""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            
            return output or f"(Command completed with exit code {result.returncode})"
        except subprocess.TimeoutExpired:
            raise ToolError(self.name, f"Command timed out after {timeout}s", "TIMEOUT")
        except Exception as e:
            raise ToolError(self.name, str(e), "EXEC_ERROR")


@register_tool("edit_file")
class EditFileTool(BaseTool):
    """Edit a file by replacing a substring."""
    
    name = "edit_file"
    schema = {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit a file by replacing old content with new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to edit"
                    },
                    "old_str": {
                        "type": "string",
                        "description": "The exact string to find and replace"
                    },
                    "new_str": {
                        "type": "string",
                        "description": "The new content to replace with"
                    }
                },
                "required": ["file_path", "old_str", "new_str"]
            }
        }
    }

    def call(self, file_path: str, old_str: str, new_str: str, **kwargs) -> str:
        """Edit file by replacing substring."""
        try:
            file_path = Path(file_path).expanduser()
            if not file_path.exists():
                raise ToolError(self.name, f"File not found: {file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_str not in content:
                raise ToolError(
                    self.name,
                    f"String not found in file: {old_str[:50]}...",
                    "NOT_FOUND"
                )
            
            # Replace only first occurrence to avoid accidental bulk changes
            new_content = content.replace(old_str, new_str, 1)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return f"Successfully edited {file_path}"
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(self.name, str(e), "EDIT_ERROR")


@register_tool("apply_diff")
class ApplyDiffTool(BaseTool):
    """Apply a patch/diff to a file."""
    
    name = "apply_diff"
    schema = {
        "type": "function",
        "function": {
            "name": "apply_diff",
            "description": "Apply a unified diff/patch to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to patch"
                    },
                    "diff": {
                        "type": "string",
                        "description": "Unified diff content (unified format)"
                    }
                },
                "required": ["file_path", "diff"]
            }
        }
    }

    def call(self, file_path: str, diff: str, **kwargs) -> str:
        """Apply diff to file."""
        try:
            import tempfile
            
            file_path = Path(file_path).expanduser()
            if not file_path.exists():
                raise ToolError(self.name, f"File not found: {file_path}")
            
            # Write diff to temp file and apply with patch command
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
                f.write(diff)
                patch_file = f.name
            
            try:
                result = subprocess.run(
                    ["patch", str(file_path), patch_file],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0:
                    raise ToolError(
                        self.name,
                        f"Patch failed: {result.stderr}",
                        "PATCH_ERROR"
                    )
                
                return f"Successfully applied patch to {file_path}"
            finally:
                os.unlink(patch_file)
        except subprocess.TimeoutExpired:
            raise ToolError(self.name, "Patch timed out", "TIMEOUT")
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(self.name, str(e), "APPLY_DIFF_ERROR")
