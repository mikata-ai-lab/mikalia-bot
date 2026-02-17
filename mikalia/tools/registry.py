"""
registry.py — Registro central de tools de Mikalia.

Descubre, registra y ejecuta tools. Genera las definiciones
que Claude API necesita para tool_use.

Uso:
    from mikalia.tools.registry import ToolRegistry
    registry = ToolRegistry.with_defaults()
    definitions = registry.get_tool_definitions()
    result = registry.execute("file_read", {"path": "README.md"})
"""

from __future__ import annotations

from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.registry")


class ToolRegistry:
    """
    Registro central de tools disponibles.

    Descubre, registra y ejecuta tools. Genera las definiciones
    que Claude API necesita para tool_use.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registra un tool en el registry."""
        self._tools[tool.name] = tool
        logger.info(f"Tool registrado: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        """Obtiene un tool por nombre."""
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """
        Genera las definiciones de tools para Claude API.

        Returns:
            Lista de dicts compatibles con el parametro `tools`
            de messages.create().
        """
        return [tool.to_claude_definition() for tool in self._tools.values()]

    def execute(self, tool_name: str, params: dict[str, Any]) -> ToolResult:
        """
        Ejecuta un tool por nombre con los parametros dados.

        Args:
            tool_name: Nombre del tool a ejecutar.
            params: Parametros para el tool.

        Returns:
            ToolResult con el resultado de la ejecucion.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool no encontrado: '{tool_name}'. "
                f"Disponibles: {', '.join(self._tools.keys())}",
            )

        try:
            return tool.execute(**params)
        except Exception as e:
            logger.error(f"Error ejecutando tool '{tool_name}': {e}")
            return ToolResult(success=False, error=str(e))

    def list_tools(self) -> list[str]:
        """Lista los nombres de todos los tools registrados."""
        return list(self._tools.keys())

    @classmethod
    def with_defaults(cls) -> ToolRegistry:
        """Crea un registry con los tools por defecto de Mikalia."""
        registry = cls()

        from mikalia.tools.file_ops import (
            FileReadTool,
            FileWriteTool,
            FileListTool,
        )

        registry.register(FileReadTool())
        registry.register(FileWriteTool())
        registry.register(FileListTool())

        return registry
