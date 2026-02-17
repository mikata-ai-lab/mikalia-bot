"""
git_ops.py — Tool de operaciones Git para Mikalia.

Permite ejecutar operaciones Git comunes de forma segura.
Bloquea operaciones peligrosas (force push, reset --hard, etc.)

Uso:
    from mikalia.tools.git_ops import GitStatusTool, GitCommitTool
    tool = GitStatusTool()
    result = tool.execute(repo_path="/path/to/repo")
"""

from __future__ import annotations

import subprocess
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.git_ops")


def _run_git(args: list[str], cwd: str | None = None) -> ToolResult:
    """Helper para ejecutar comandos git."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )

        output = result.stdout
        if result.stderr:
            output += result.stderr

        if result.returncode != 0:
            return ToolResult(
                success=False,
                error=f"git {' '.join(args)}: {output}",
            )

        return ToolResult(success=True, output=output or "(sin output)")

    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error="Git timeout (30s)")
    except FileNotFoundError:
        return ToolResult(success=False, error="Git no encontrado en PATH")


class GitStatusTool(BaseTool):
    """Muestra el estado del repositorio Git."""

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Show git status of a repository (modified files, branch, etc.)"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository",
                    "default": ".",
                },
            },
            "required": [],
        }

    def execute(self, repo_path: str = ".", **_: Any) -> ToolResult:
        return _run_git(["status", "--short", "--branch"], cwd=repo_path)


class GitDiffTool(BaseTool):
    """Muestra los cambios pendientes en el repositorio."""

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return "Show git diff of pending changes in a repository"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository",
                    "default": ".",
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes only",
                    "default": False,
                },
            },
            "required": [],
        }

    def execute(
        self, repo_path: str = ".", staged: bool = False, **_: Any
    ) -> ToolResult:
        args = ["diff"]
        if staged:
            args.append("--cached")
        args.append("--stat")
        return _run_git(args, cwd=repo_path)


class GitLogTool(BaseTool):
    """Muestra el historial reciente de commits."""

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "Show recent git commit history"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository",
                    "default": ".",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show",
                    "default": 10,
                },
            },
            "required": [],
        }

    def execute(
        self, repo_path: str = ".", count: int = 10, **_: Any
    ) -> ToolResult:
        return _run_git(
            ["log", f"-{count}", "--oneline", "--decorate"],
            cwd=repo_path,
        )
