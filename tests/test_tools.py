"""
test_tools.py — Tests para el sistema de tools de Mikalia.

Verifica:
- BaseTool interface y ToolResult
- ToolRegistry: registro, descubrimiento, ejecucion
- FileReadTool, FileWriteTool, FileListTool
- Formato de tool definitions para Claude API
"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.tools.registry import ToolRegistry
from mikalia.tools.file_ops import FileReadTool, FileWriteTool, FileListTool


# ================================================================
# ToolResult
# ================================================================

class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, output="OK")
        assert result.success
        assert result.output == "OK"
        assert result.error == ""

    def test_error_result(self):
        result = ToolResult(success=False, error="Fallo")
        assert not result.success
        assert result.error == "Fallo"


# ================================================================
# ToolRegistry
# ================================================================

class TestToolRegistry:
    def test_register_tool(self):
        registry = ToolRegistry()
        tool = FileReadTool()
        registry.register(tool)
        assert "file_read" in registry.list_tools()

    def test_get_tool(self):
        registry = ToolRegistry()
        tool = FileReadTool()
        registry.register(tool)
        assert registry.get("file_read") is tool

    def test_get_missing_tool_returns_none(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_get_tool_definitions_format(self):
        """Las definiciones tienen el formato que Claude API espera."""
        registry = ToolRegistry()
        registry.register(FileReadTool())

        definitions = registry.get_tool_definitions()
        assert len(definitions) == 1

        d = definitions[0]
        assert "name" in d
        assert "description" in d
        assert "input_schema" in d
        assert d["input_schema"]["type"] == "object"
        assert "properties" in d["input_schema"]

    def test_execute_registered_tool(self, tmp_path):
        """Ejecutar un tool registrado funciona."""
        # Crear archivo temporal
        test_file = tmp_path / "hello.txt"
        test_file.write_text("Hello World", encoding="utf-8")

        registry = ToolRegistry()
        registry.register(FileReadTool())

        result = registry.execute("file_read", {"path": str(test_file)})
        assert result.success
        assert "Hello World" in result.output

    def test_execute_unknown_tool_returns_error(self):
        """Ejecutar un tool que no existe retorna error."""
        registry = ToolRegistry()
        result = registry.execute("nonexistent", {})
        assert not result.success
        assert "no encontrado" in result.error.lower()

    def test_with_defaults_loads_file_tools(self):
        """with_defaults() carga los 3 file tools."""
        registry = ToolRegistry.with_defaults()
        tools = registry.list_tools()
        assert "file_read" in tools
        assert "file_write" in tools
        assert "file_list" in tools


# ================================================================
# FileReadTool
# ================================================================

class TestFileReadTool:
    def test_read_existing_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("contenido de prueba", encoding="utf-8")

        tool = FileReadTool()
        result = tool.execute(path=str(test_file))
        assert result.success
        assert "contenido de prueba" in result.output

    def test_read_missing_file(self):
        tool = FileReadTool()
        result = tool.execute(path="/nonexistent/file.txt")
        assert not result.success
        assert "no encontrado" in result.error.lower()

    def test_read_with_max_lines(self, tmp_path):
        test_file = tmp_path / "multi.txt"
        test_file.write_text("linea1\nlinea2\nlinea3\nlinea4\nlinea5", encoding="utf-8")

        tool = FileReadTool()
        result = tool.execute(path=str(test_file), max_lines=2)
        assert result.success
        assert "linea1" in result.output
        assert "linea2" in result.output
        assert "3 lineas mas" in result.output

    def test_claude_definition_format(self):
        tool = FileReadTool()
        definition = tool.to_claude_definition()
        assert definition["name"] == "file_read"
        assert "path" in definition["input_schema"]["properties"]
        assert "path" in definition["input_schema"]["required"]


# ================================================================
# FileWriteTool
# ================================================================

class TestFileWriteTool:
    def test_write_new_file(self, tmp_path):
        target = tmp_path / "nuevo.txt"
        tool = FileWriteTool()
        result = tool.execute(path=str(target), content="Hola Mikalia")
        assert result.success
        assert target.read_text(encoding="utf-8") == "Hola Mikalia"

    def test_write_creates_directories(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "file.txt"
        tool = FileWriteTool()
        result = tool.execute(path=str(target), content="deep write")
        assert result.success
        assert target.exists()

    def test_overwrite_existing_file(self, tmp_path):
        target = tmp_path / "existing.txt"
        target.write_text("viejo", encoding="utf-8")

        tool = FileWriteTool()
        tool.execute(path=str(target), content="nuevo")
        assert target.read_text(encoding="utf-8") == "nuevo"


# ================================================================
# FileListTool
# ================================================================

class TestFileListTool:
    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.py").write_text("b", encoding="utf-8")
        (tmp_path / "subdir").mkdir()

        tool = FileListTool()
        result = tool.execute(path=str(tmp_path))
        assert result.success
        assert "a.txt" in result.output
        assert "b.py" in result.output
        assert "subdir/" in result.output

    def test_list_with_pattern(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.py").write_text("b", encoding="utf-8")

        tool = FileListTool()
        result = tool.execute(path=str(tmp_path), pattern="*.py")
        assert result.success
        assert "b.py" in result.output
        assert "a.txt" not in result.output

    def test_list_missing_directory(self):
        tool = FileListTool()
        result = tool.execute(path="/nonexistent/dir")
        assert not result.success
        assert "no encontrado" in result.error.lower()
