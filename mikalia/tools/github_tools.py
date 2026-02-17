"""
github_tools.py — Tools de Git y GitHub para Mikalia Core.

Permite a Mikalia hacer commits, push, y crear PRs.
Usa subprocess para git y gh CLI.

Seguridad:
- NUNCA force push
- NUNCA toca archivos .env o secrets
- Siempre verifica que el repo sea valido

Uso:
    from mikalia.tools.github_tools import GitCommitTool
    tool = GitCommitTool()
    result = tool.execute(repo_path=".", files=["README.md"], message="Update readme")
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.github")

# Archivos que NUNCA se deben commitear
BLOCKED_FILES = {
    ".env", ".env.local", ".env.production",
    "credentials.json", "service-account.json",
    "id_rsa", "id_ed25519", "*.pem", "*.key",
}

# Ruta de gh CLI en Windows (no esta en PATH)
GH_CLI = r"C:\Program Files\GitHub CLI\gh.exe"


def _is_blocked_file(filename: str) -> bool:
    """Verifica si un archivo esta bloqueado por seguridad."""
    name = Path(filename).name.lower()
    for pattern in BLOCKED_FILES:
        if pattern.startswith("*"):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern.lower():
            return True
    return False


def _run_git(args: list[str], cwd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Ejecuta un comando git."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class GitCommitTool(BaseTool):
    """Hace git add + commit en un repositorio."""

    @property
    def name(self) -> str:
        return "git_commit"

    @property
    def description(self) -> str:
        return (
            "Stage files and create a git commit. "
            "Provide the repo path, list of files to add, and commit message. "
            "Files like .env and credentials are blocked for security. "
            "Use '.' as repo_path for the current directory."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository",
                    "default": ".",
                },
                "files": {
                    "type": "string",
                    "description": "Files to stage, comma-separated (e.g. 'src/main.py, README.md'). Use 'all' for git add -A.",
                },
                "message": {
                    "type": "string",
                    "description": "Commit message",
                },
            },
            "required": ["files", "message"],
        }

    def execute(
        self,
        files: str,
        message: str,
        repo_path: str = ".",
        **_: Any,
    ) -> ToolResult:
        repo = Path(repo_path)
        if not (repo / ".git").exists() and repo_path != ".":
            return ToolResult(success=False, error=f"No es un repo git: {repo_path}")

        # Parsear archivos
        if files.strip().lower() == "all":
            file_list = ["-A"]
        else:
            file_list = [f.strip() for f in files.split(",") if f.strip()]

        # Verificar archivos bloqueados
        if file_list != ["-A"]:
            for f in file_list:
                if _is_blocked_file(f):
                    return ToolResult(
                        success=False,
                        error=f"Archivo bloqueado por seguridad: {f}",
                    )

        try:
            # git add
            result = _run_git(["add"] + file_list, cwd=str(repo))
            if result.returncode != 0 and "fatal" in (result.stderr or ""):
                return ToolResult(success=False, error=f"git add fallo: {result.stderr}")

            # git commit
            result = _run_git(["commit", "-m", message], cwd=str(repo))

            if result.returncode != 0:
                stderr = result.stderr or result.stdout
                if "nothing to commit" in stderr:
                    return ToolResult(success=True, output="Nada que commitear — el repo esta limpio.")
                return ToolResult(success=False, error=f"git commit fallo: {stderr}")

            # Extraer hash corto
            hash_result = _run_git(["rev-parse", "--short", "HEAD"], cwd=str(repo))
            short_hash = hash_result.stdout.strip()

            logger.success(f"Commit {short_hash}: {message}")
            return ToolResult(
                success=True,
                output=f"Commit creado: {short_hash}\nMensaje: {message}",
            )

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="Timeout en git commit")
        except Exception as e:
            return ToolResult(success=False, error=f"Error: {e}")


class GitPushTool(BaseTool):
    """Pushea cambios al remoto."""

    @property
    def name(self) -> str:
        return "git_push"

    @property
    def description(self) -> str:
        return (
            "Push commits to the remote repository. "
            "Optionally specify a branch. Force push is NEVER allowed."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository",
                    "default": ".",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch to push (default: current branch)",
                    "default": "",
                },
            },
            "required": [],
        }

    def execute(
        self,
        repo_path: str = ".",
        branch: str = "",
        **_: Any,
    ) -> ToolResult:
        try:
            args = ["push"]
            if branch:
                args.extend(["-u", "origin", branch])

            result = _run_git(args, cwd=repo_path, timeout=60)

            if result.returncode != 0:
                stderr = result.stderr or ""
                if "up-to-date" in stderr or "Everything up-to-date" in stderr:
                    return ToolResult(success=True, output="Ya esta actualizado con el remoto.")
                return ToolResult(success=False, error=f"git push fallo: {stderr}")

            logger.success(f"Push exitoso: {repo_path}")
            return ToolResult(
                success=True,
                output=f"Push exitoso.\n{result.stderr or result.stdout}".strip(),
            )

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="Timeout en git push (>60s)")
        except Exception as e:
            return ToolResult(success=False, error=f"Error: {e}")


class GitBranchTool(BaseTool):
    """Crea o cambia de branch."""

    @property
    def name(self) -> str:
        return "git_branch"

    @property
    def description(self) -> str:
        return (
            "Create a new branch or switch to an existing one. "
            "Use action 'create' to make a new branch, 'switch' to checkout."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository",
                    "default": ".",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Branch name (e.g. 'mikalia/feat/add-validation')",
                },
                "action": {
                    "type": "string",
                    "description": "'create' for new branch, 'switch' to checkout existing",
                    "default": "create",
                },
            },
            "required": ["branch_name"],
        }

    def execute(
        self,
        branch_name: str,
        repo_path: str = ".",
        action: str = "create",
        **_: Any,
    ) -> ToolResult:
        try:
            if action == "create":
                result = _run_git(["checkout", "-b", branch_name], cwd=repo_path)
            else:
                result = _run_git(["checkout", branch_name], cwd=repo_path)

            if result.returncode != 0:
                return ToolResult(success=False, error=f"git branch fallo: {result.stderr}")

            logger.success(f"Branch: {branch_name} ({action})")
            return ToolResult(
                success=True,
                output=f"Branch '{branch_name}' — {action} exitoso.",
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Error: {e}")


class GitHubPRTool(BaseTool):
    """Crea Pull Requests en GitHub usando gh CLI."""

    @property
    def name(self) -> str:
        return "github_pr"

    @property
    def description(self) -> str:
        return (
            "Create a Pull Request on GitHub. Requires gh CLI. "
            "The current branch will be used as the head branch. "
            "Always create a new branch first (git_branch), commit, "
            "push, then use this tool to create the PR."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to the git repository",
                    "default": ".",
                },
                "title": {
                    "type": "string",
                    "description": "PR title",
                },
                "body": {
                    "type": "string",
                    "description": "PR description (markdown)",
                },
                "base": {
                    "type": "string",
                    "description": "Base branch (default: main)",
                    "default": "main",
                },
                "labels": {
                    "type": "string",
                    "description": "Comma-separated labels (e.g. 'enhancement,mikalia-authored')",
                    "default": "mikalia-authored",
                },
            },
            "required": ["title", "body"],
        }

    def execute(
        self,
        title: str,
        body: str,
        repo_path: str = ".",
        base: str = "main",
        labels: str = "mikalia-authored",
        **_: Any,
    ) -> ToolResult:
        # Buscar gh CLI
        gh = self._find_gh()
        if not gh:
            return ToolResult(
                success=False,
                error="gh CLI no encontrado. Instala GitHub CLI.",
            )

        try:
            cmd = [
                gh, "pr", "create",
                "--title", title,
                "--body", body,
                "--base", base,
            ]

            if labels:
                for label in labels.split(","):
                    cmd.extend(["--label", label.strip()])

            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr or result.stdout
                return ToolResult(success=False, error=f"gh pr create fallo: {stderr}")

            pr_url = result.stdout.strip()
            logger.success(f"PR creado: {pr_url}")
            return ToolResult(
                success=True,
                output=f"PR creado exitosamente!\nURL: {pr_url}",
            )

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="Timeout creando PR")
        except Exception as e:
            return ToolResult(success=False, error=f"Error: {e}")

    @staticmethod
    def _find_gh() -> str | None:
        """Busca gh CLI en el sistema."""
        # Windows: ruta conocida
        gh_path = Path(GH_CLI)
        if gh_path.exists():
            return str(gh_path)

        # Intentar en PATH
        try:
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return "gh"
        except Exception:
            pass

        return None
