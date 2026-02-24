"""
base.py — Interfaz base para tools de Mikalia.

Cada tool hereda de BaseTool y se registra en el ToolRegistry.
El ToolRegistry genera las definiciones que Claude API espera
para tool_use.

Uso:
    from mikalia.tools.base import BaseTool, ToolResult

    class MyTool(BaseTool):
        name = "my_tool"
        description = "Hace algo util"
        ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """
    Resultado de la ejecucion de un tool.

    Campos:
        success: Si la ejecucion fue exitosa.
        output: Resultado de la ejecucion (texto, datos, etc.)
        error: Mensaje de error si fallo.
    """

    success: bool
    output: str = ""
    error: str = ""


class BaseTool(ABC):
    """
    Interfaz base para tools de Mikalia.

    Cada tool debe implementar:
    - name: Nombre unico del tool (usado por Claude para invocarlo)
    - description: Descripcion breve (Claude la lee para decidir cuando usar)
    - get_parameters(): JSON Schema de los parametros que acepta
    - execute(): Logica de ejecucion
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre unico del tool."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Descripcion breve para Claude."""
        ...

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """JSON Schema de los parametros que acepta."""
        ...

    def execute(self, **params: Any) -> ToolResult:
        """Ejecuta el tool con los parametros dados.

        Las subclases definen parametros con nombre (e.g., execute(self, code, timeout))
        y **_ para absorber extras. No usamos @abstractmethod para evitar
        conflictos de signature con mypy en las 44 implementaciones.
        """
        raise NotImplementedError(f"{self.__class__.__name__}.execute() no implementado")

    def to_claude_definition(self) -> dict[str, Any]:
        """
        Genera la definicion de tool en formato Claude API.

        Returns:
            Dict compatible con el parametro `tools` de messages.create().
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_parameters(),
        }
