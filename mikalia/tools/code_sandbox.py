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

# Modulos permitidos (whitelist — todo lo demas se bloquea)
ALLOWED_MODULES = {
    "math", "json", "re", "datetime", "collections", "itertools",
    "statistics", "random", "string", "textwrap", "csv", "io",
    "decimal", "fractions", "operator", "functools", "typing",
    "dataclasses", "enum", "copy", "pprint", "bisect", "heapq",
    "array", "struct", "hashlib", "base64", "html", "urllib.parse",
    "time",
}

# Patrones peligrosos en codigo (case-insensitive)
BLOCKED_PATTERNS = [
    "open(", "eval(", "exec(",
    "__builtins__", "__class__", "__subclasses__",
    "__import__", "__globals__", "__code__",
    "globals(", "locals(", "vars(",
    "getattr(", "setattr(", "delattr(",
    "compile(", "breakpoint(",
    ".env", "api_key", "secret", "token", "password",
    "rm -rf", "os.remove", "os.unlink",
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

        # Bloquear patrones peligrosos
        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in code_lower:
                return f"Codigo bloqueado: patron peligroso detectado ({pattern})"

        # Bloquear string concatenation bypass (e.g., 'ev'+'al')
        concat_patterns = ["'+'", '"+"', "'+\"", "\"+'" ]
        for cp in concat_patterns:
            if cp in code:
                return "Codigo bloqueado: concatenacion de strings sospechosa"

        # Whitelist de imports — solo permitir modulos seguros
        import re
        import_pattern = re.compile(
            r"(?:^|;|\n)\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)",
        )
        for match in import_pattern.finditer(code):
            module = match.group(1).split(".")[0]
            if module not in ALLOWED_MODULES:
                return f"Import bloqueado: '{module}' no esta en la whitelist de modulos seguros"

        return None
