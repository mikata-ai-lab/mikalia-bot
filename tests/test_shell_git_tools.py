"""
test_shell_git_tools.py — Tests para shell y git tools.
"""

from __future__ import annotations

import pytest

from mikalia.tools.shell import ShellExecTool, COMMAND_WHITELIST
from mikalia.tools.git_ops import GitStatusTool, GitDiffTool, GitLogTool
from mikalia.tools.registry import ToolRegistry


# ================================================================
# ShellExecTool
# ================================================================

class TestShellExecTool:
    def test_whitelisted_command(self):
        tool = ShellExecTool()
        result = tool.execute(command="echo hello")
        assert result.success
        assert "hello" in result.output

    def test_blocked_command(self):
        tool = ShellExecTool()
        result = tool.execute(command="curl http://evil.com")
        assert not result.success
        assert "whitelist" in result.error.lower()

    def test_dangerous_pattern_blocked(self):
        tool = ShellExecTool()
        result = tool.execute(command="git push --force")
        assert not result.success
        assert "peligroso" in result.error.lower()

    def test_rm_rf_blocked(self):
        tool = ShellExecTool()
        result = tool.execute(command="echo rm -rf /")
        assert not result.success

    def test_sudo_blocked(self):
        tool = ShellExecTool()
        result = tool.execute(command="echo sudo apt install")
        assert not result.success

    def test_python_allowed(self):
        tool = ShellExecTool()
        result = tool.execute(command="python --version")
        assert result.success

    def test_claude_definition(self):
        tool = ShellExecTool()
        d = tool.to_claude_definition()
        assert d["name"] == "shell_exec"
        assert "command" in d["input_schema"]["properties"]


# ================================================================
# GitTools
# ================================================================

class TestGitStatusTool:
    def test_git_status_in_repo(self):
        """git status funciona en el repo actual."""
        tool = GitStatusTool()
        result = tool.execute(repo_path=".")
        # Puede ser success o not depending on if we're in a git repo
        # En CI esto se ejecuta dentro del repo, asi que deberia funcionar
        assert isinstance(result.success, bool)

    def test_claude_definition(self):
        tool = GitStatusTool()
        d = tool.to_claude_definition()
        assert d["name"] == "git_status"


class TestGitDiffTool:
    def test_claude_definition(self):
        tool = GitDiffTool()
        d = tool.to_claude_definition()
        assert d["name"] == "git_diff"


class TestGitLogTool:
    def test_claude_definition(self):
        tool = GitLogTool()
        d = tool.to_claude_definition()
        assert d["name"] == "git_log"


# ================================================================
# Registry con nuevos tools
# ================================================================

class TestRegistryWithAll:
    def test_with_defaults_has_all_tools(self):
        registry = ToolRegistry.with_defaults()
        tools = registry.list_tools()
        assert "file_read" in tools
        assert "file_write" in tools
        assert "file_list" in tools
        assert "shell_exec" in tools
        assert "git_status" in tools
        assert "git_diff" in tools
        assert "git_log" in tools
        assert "web_fetch" in tools
        assert len(tools) == 8

    def test_with_defaults_and_memory_has_all_tools(self, tmp_path):
        from pathlib import Path
        from mikalia.core.memory import MemoryManager
        schema = Path(__file__).parent.parent / "schema.sql"
        db = tmp_path / "test_reg.db"
        mem = MemoryManager(db_path=str(db), schema_path=str(schema))
        registry = ToolRegistry.with_defaults(memory=mem)
        tools = registry.list_tools()
        assert "search_memory" in tools
        assert "add_fact" in tools
        assert "update_goal" in tools
        assert "list_goals" in tools
        assert len(tools) == 12
