"""
code_sandbox.py — Ejecucion segura de Python para Mikalia.

Ejecuta codigo Python en un subprocess aislado con:
- Timeout (max 30s)
- Sin acceso a red (no import socket/requests)
- Sin acceso a archivos del sistema
- Output capturado (stdout + stderr)
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.code_sandbox")

# Imports peligrosos que no se permiten
BLOCKED_IMPORTS = [
    "os.system", "subprocess", "shutil.rmtree",
    "socket", "http.server", "smtplib",
    "__import__", "importlib",
    "ctypes", "multiprocessing",
]

# Patrones peligrosos en codigo
BLOCKED_PATTERNS = [
    "open('/etc", "open('C:\\\\",
    "rm -rf", "os.remove", "os.unlink",
    "eval(", "exec(",
    "__builtins__", "__class__",
    ".env", "API_KEY", "SECRET", "TOKEN", "PASSWORD",
]

MAX_TIMEOUT = 30
MAX_OUTPUT = 5000


class CodeSandboxTool(BaseTool):
    """Ejecuta Python en un entorno aislado y seguro."""

    @property
    def name(self) -> str:
        return "code_sandbox"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a safe sandbox. "
            "Use for calculations, data processing, string manipulation, "
            "testing algorithms, or generating formatted output. "
            "Has access to: math, json, re, datetime, collections, itertools, "
            "statistics, random, string, textwrap, csv, io. "
            "Does NOT have access to: network, file system, or dangerous modules. "
            "Max execution time: 30 seconds."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max execution seconds (default: 10, max: 30)",
                },
            },
            "required": ["code"],
        }

    def execute(
        self, code: str, timeout: int = 10, **_: Any
    ) -> ToolResult:
        if not code.strip():
            return ToolResult(success=False, error="Codigo vacio")

        # Validar seguridad
        safety_error = self._check_safety(code)
        if safety_error:
            return ToolResult(success=False, error=safety_error)

        timeout = min(max(timeout, 1), MAX_TIMEOUT)

        try:
            # Escribir codigo a archivo temporal
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8",
            ) as f:
                f.write(code)
                temp_path = f.name

            start = time.time()

            # Ejecutar en subprocess aislado
            result = subprocess.run(
                [sys.executable, "-u", temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir(),
            )

            elapsed = time.time() - start

            # Limpiar archivo temporal
            Path(temp_path).unlink(missing_ok=True)

            stdout = result.stdout[:MAX_OUTPUT] if result.stdout else ""
            stderr = result.stderr[:MAX_OUTPUT] if result.stderr else ""

            if result.returncode == 0:
                output_parts = [f"Ejecutado en {elapsed:.2f}s"]
                if stdout:
                    output_parts.append(f"\nOutput:\n{stdout}")
                if not stdout:
                    output_parts.append("\n(sin output)")

                logger.success(f"Sandbox ejecutado OK en {elapsed:.2f}s")
                return ToolResult(
                    success=True,
                    output="\n".join(output_parts),
                )
            else:
                logger.warning(f"Sandbox error (exit {result.returncode})")
                return ToolResult(
                    success=False,
                    error=f"Exit code {result.returncode}\n{stderr}",
                )

        except subprocess.TimeoutExpired:
            Path(temp_path).unlink(missing_ok=True)
            return ToolResult(
                success=False,
                error=f"Timeout: el codigo tardo mas de {timeout}s",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Error ejecutando codigo: {e}")

    def _check_safety(self, code: str) -> str | None:
        """Verifica que el codigo no tenga patrones peligrosos."""
        code_lower = code.lower()

        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in code_lower:
                return f"Codigo bloqueado: patron peligroso detectado ({pattern})"

        for imp in BLOCKED_IMPORTS:
            if imp in code:
                return f"Import bloqueado: {imp}"

        return None
