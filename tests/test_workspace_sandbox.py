"""Tests for workspace sandboxing in builtin_llama tools."""

import os
import tempfile

import pytest

from tools.base import get_tool, ToolError


class TestWorkspaceSandbox:
    """Verify _validate_workspace_path rejects paths outside WORKSPACE_ROOT."""

    def test_read_file_rejects_outside_workspace(self, monkeypatch):
        monkeypatch.setattr("config.WORKSPACE_ROOT", "/tmp/fake_workspace")

        tool = get_tool("read_file")
        with pytest.raises(ToolError, match="PATH_DENIED"):
            tool.call(file_path="/etc/passwd")

    def test_read_file_rejects_traversal(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("config.WORKSPACE_ROOT", tmpdir)

            tool = get_tool("read_file")
            with pytest.raises(ToolError, match="PATH_DENIED"):
                tool.call(file_path="../../../etc/passwd")

    def test_read_file_allows_workspace_path(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("config.WORKSPACE_ROOT", tmpdir)

            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("hello workspace")

            tool = get_tool("read_file")
            result = tool.call(file_path=test_file)
            assert "hello workspace" in result
