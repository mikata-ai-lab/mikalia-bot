"""
file_ops.py — Tools de operaciones de archivos para Mikalia.

Tres herramientas que Mikalia puede usar autonomamente:
- file_read:  Leer contenido de archivos
- file_write: Escribir/crear archivos
- file_list:  Listar directorio

Uso:
    from mikalia.tools.file_ops import FileReadTool
    tool = FileReadTool()
    result = tool.execute(path="README.md")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult


class FileReadTool(BaseTool):
    """Lee el contenido de un archivo."""

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Maximum lines to read (0 = all)",
                    "default": 0,
                },
            },
            "required": ["path"],
        }

    def execute(self, path: str, max_lines: int = 0, **_: Any) -> ToolResult:
        """Lee un archivo y retorna su contenido."""
        try:
            file_path = Path(path)
            if not file_path.exists():
                return ToolResult(
                    success=False,
                    error=f"Archivo no encontrado: {path}",
                )
            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    error=f"No es un archivo: {path}",
                )

            content = file_path.read_text(encoding="utf-8", errors="replace")

            if max_lines > 0:
                lines = content.splitlines()
                content = "\n".join(lines[:max_lines])
                if len(lines) > max_lines:
                    content += f"\n... ({len(lines) - max_lines} lineas mas)"

            return ToolResult(success=True, output=content)

        except PermissionError:
            return ToolResult(
                success=False,
                error=f"Sin permisos para leer: {path}",
            )
        except OSError as e:
            return ToolResult(success=False, error=f"Error de I/O: {e}")


class FileWriteTool(BaseTool):
    """Escribe contenido a un archivo, creando directorios si es necesario."""

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Write content to a file, creating directories if needed"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    def execute(self, path: str, content: str, **_: Any) -> ToolResult:
        """Escribe contenido a un archivo."""
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

            size = file_path.stat().st_size
            return ToolResult(
                success=True,
                output=f"Archivo escrito: {path} ({size} bytes)",
            )

        except PermissionError:
            return ToolResult(
                success=False,
                error=f"Sin permisos para escribir: {path}",
            )
        except OSError as e:
            return ToolResult(success=False, error=f"Error de I/O: {e}")


class FileListTool(BaseTool):
    """Lista archivos y directorios en una ruta."""

    @property
    def name(self) -> str:
        return "file_list"

    @property
    def description(self) -> str:
        return "List files and directories at the given path"

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern filter (e.g. '*.py')",
                    "default": "*",
                },
            },
            "required": [],
        }

    def execute(
        self, path: str = ".", pattern: str = "*", **_: Any
    ) -> ToolResult:
        """Lista contenido de un directorio."""
        try:
            dir_path = Path(path)
            if not dir_path.exists():
                return ToolResult(
                    success=False,
                    error=f"Directorio no encontrado: {path}",
                )
            if not dir_path.is_dir():
                return ToolResult(
                    success=False,
                    error=f"No es un directorio: {path}",
                )

            entries = sorted(dir_path.glob(pattern))
            lines = []
            for entry in entries:
                if entry.is_dir():
                    lines.append(f"  {entry.name}/")
                else:
                    size = entry.stat().st_size
                    lines.append(f"  {entry.name} ({size} bytes)")

            output = f"{path}/\n" + "\n".join(lines) if lines else f"{path}/ (vacio)"
            return ToolResult(success=True, output=output)

        except PermissionError:
            return ToolResult(
                success=False,
                error=f"Sin permisos para listar: {path}",
            )
        except OSError as e:
            return ToolResult(success=False, error=f"Error de I/O: {e}")
