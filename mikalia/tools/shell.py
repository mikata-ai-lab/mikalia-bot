"""
shell.py — Tool de ejecucion de comandos shell para Mikalia.

Permite ejecutar comandos del sistema con whitelist de seguridad.
Solo permite comandos aprobados para prevenir acciones peligrosas.

Nota: Maneja diferencias entre Windows (cmd.exe) y Unix (bash).
Por ejemplo, `mkdir -p` se convierte a os.makedirs en Windows.

Uso:
    from mikalia.tools.shell import ShellExecTool
    tool = ShellExecTool()
    result = tool.execute(command="git status")
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.shell")

# Comandos permitidos (primer token del comando)
COMMAND_WHITELIST = {
    "git", "hugo", "ls", "dir", "cat", "echo", "python", "pip",
    "npm", "node", "pytest", "ruff", "mypy", "type", "where",
    "pwd", "cd", "mkdir", "cp", "mv", "head", "tail", "wc",
}

# Patrones peligrosos (bloquear siempre)
DANGEROUS_PATTERNS = [
    "rm -rf", "del /f", "format c:", "sudo", "chmod 777",
    "DROP TABLE", "DROP DATABASE", "DELETE FROM",
    "os.system", "subprocess.call", "eval(", "exec(",
    "--force", "push --force", "reset --hard",
]


class ShellExecTool(BaseTool):
    """Ejecuta comandos shell con whitelist de seguridad."""

    @property
    def name(self) -> str:
        return "shell_exec"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command. Only whitelisted commands are allowed: "
            "git, hugo, python, pip, npm, pytest, ls, mkdir, etc. "
            "Dangerous patterns like rm -rf, sudo, --force are blocked."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (optional)",
                    "default": ".",
                },
            },
            "required": ["command"],
        }

    def execute(
        self, command: str, cwd: str = ".", **_: Any
    ) -> ToolResult:
        """Ejecuta un comando shell con validacion de seguridad."""
        # Validar contra patrones peligrosos
        for pattern in DANGEROUS_PATTERNS:
            if pattern.lower() in command.lower():
                return ToolResult(
                    success=False,
                    error=f"Comando bloqueado: contiene patron peligroso '{pattern}'",
                )

        # Validar whitelist
        first_token = command.strip().split()[0] if command.strip() else ""
        if first_token not in COMMAND_WHITELIST:
            return ToolResult(
                success=False,
                error=(
                    f"Comando '{first_token}' no esta en la whitelist. "
                    f"Permitidos: {', '.join(sorted(COMMAND_WHITELIST))}"
                ),
            )

        # Windows compat: mkdir -p no existe en cmd.exe
        # Usamos os.makedirs directamente
        handled = self._handle_cross_platform(command, cwd)
        if handled is not None:
            return handled

        logger.info(f"Ejecutando: {command}")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd if cwd != "." else None,
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"

            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Exit code {result.returncode}:\n{output}",
                )

            return ToolResult(success=True, output=output or "(sin output)")

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error="Timeout: el comando tardo mas de 30 segundos",
            )
        except OSError as e:
            return ToolResult(success=False, error=f"Error de sistema: {e}")

    def _handle_cross_platform(
        self, command: str, cwd: str
    ) -> ToolResult | None:
        """
        Maneja comandos que difieren entre Windows y Unix.

        Retorna ToolResult si el comando fue manejado, None si no.
        """
        stripped = command.strip()

        # mkdir -p <path> → os.makedirs (cross-platform)
        if stripped.startswith("mkdir"):
            parts = stripped.split()
            # Quitar flags como -p, -m, etc
            dirs = [p for p in parts[1:] if not p.startswith("-")]
            if not dirs:
                return ToolResult(
                    success=False, error="mkdir: falta la ruta del directorio"
                )
            try:
                base = Path(cwd) if cwd != "." else Path.cwd()
                for d in dirs:
                    target = base / d if not Path(d).is_absolute() else Path(d)
                    target.mkdir(parents=True, exist_ok=True)
                    logger.info(f"Directorio creado: {target}")
                return ToolResult(
                    success=True,
                    output=f"Directorio(s) creado(s): {', '.join(dirs)}",
                )
            except OSError as e:
                return ToolResult(success=False, error=f"Error creando directorio: {e}")

        return None
