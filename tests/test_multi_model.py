"""
test_multi_model.py — Tests para MultiModelTool.

Verifica:
- Listado de modelos disponibles
- Query a modelo especifico (mock)
- Auto-routing segun complejidad
- Comparacion entre modelos
- Error sin client
- Metadata del tool
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call

from mikalia.tools.multi_model import MultiModelTool, MODELS, COMPLEXITY_KEYWORDS
from mikalia.tools.base import ToolResult


# ================================================================
# List models
# ================================================================

class TestListModels:
    def test_list_models(self):
        """Listar modelos no requiere client."""
        tool = MultiModelTool(client=None)
        result = tool.execute(action="models")
        assert result.success
        assert "Modelos disponibles" in result.output
        assert "haiku" in result.output.lower()
        assert "sonnet" in result.output.lower()
        assert "opus" in result.output.lower()
        # Verifica que muestra metadata de los modelos
        assert "Velocidad" in result.output
        assert "Costo" in result.output


# ================================================================
# Query
# ================================================================

class TestModelQuery:
    def test_query_specific_model(self):
        """Query a un modelo especifico usa client.generate."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "La capital de Francia es Paris."

        tool = MultiModelTool(client=mock_client)
        result = tool.execute(
            action="query",
            prompt="Cual es la capital de Francia?",
            model="haiku",
        )
        assert result.success
        assert "Paris" in result.output
        assert "Haiku" in result.output

        # Verificar que se llamo con el model ID correcto
        mock_client.generate.assert_called_once()
        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs["model"] == MODELS["haiku"]["id"]
        assert call_kwargs["max_tokens"] == 500


# ================================================================
# Auto-routing
# ================================================================

class TestAutoRouting:
    def test_auto_route_simple_to_haiku(self):
        """Prompts simples se enrutan a haiku."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "3 + 5 = 8"

        tool = MultiModelTool(client=mock_client)
        result = tool.execute(
            action="auto",
            prompt="calcula 3 + 5",
        )
        assert result.success
        assert "Auto-seleccionado" in result.output

        # Debe haber seleccionado haiku por la keyword "calcula"
        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs["model"] == MODELS["haiku"]["id"]

    def test_auto_route_complex_to_opus(self):
        """Prompts complejos se enrutan a opus."""
        mock_client = MagicMock()
        mock_client.generate.return_value = "Propuesta de arquitectura: ..."

        tool = MultiModelTool(client=mock_client)
        result = tool.execute(
            action="auto",
            prompt="diseña una arquitectura de microservicios",
        )
        assert result.success
        assert "Auto-seleccionado" in result.output

        # Debe haber seleccionado opus por las keywords "diseña" / "arquitectura"
        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs["model"] == MODELS["opus"]["id"]


# ================================================================
# Compare
# ================================================================

class TestModelCompare:
    def test_compare_models(self):
        """Comparar ejecuta el prompt en haiku y sonnet."""
        mock_client = MagicMock()
        mock_client.generate.side_effect = [
            "Respuesta rapida de haiku",
            "Respuesta detallada de sonnet",
        ]

        tool = MultiModelTool(client=mock_client)
        result = tool.execute(
            action="compare",
            prompt="Explica que es Python",
        )
        assert result.success
        assert "Haiku" in result.output
        assert "Sonnet" in result.output

        # Debe haberse llamado dos veces (haiku y sonnet)
        assert mock_client.generate.call_count == 2


# ================================================================
# Edge cases
# ================================================================

class TestMultiModelEdgeCases:
    def test_no_client_error(self):
        """Sin client, acciones que lo requieren fallan."""
        tool = MultiModelTool(client=None)

        result = tool.execute(action="query", prompt="hola")
        assert not result.success
        assert "MikaliaClient" in result.error

    def test_no_client_models_still_works(self):
        """Listar modelos funciona sin client."""
        tool = MultiModelTool(client=None)
        result = tool.execute(action="models")
        assert result.success

    def test_empty_prompt_rejected(self):
        """Prompt vacio es rechazado."""
        mock_client = MagicMock()
        tool = MultiModelTool(client=mock_client)
        result = tool.execute(action="query", prompt="")
        assert not result.success
        assert "Prompt requerido" in result.error

    def test_tool_metadata(self):
        """Metadata del tool es correcta."""
        tool = MultiModelTool()
        assert tool.name == "multi_model"
        assert "model" in tool.description.lower() or "Route" in tool.description

        defn = tool.to_claude_definition()
        assert defn["name"] == "multi_model"
        assert "input_schema" in defn
        assert "action" in defn["input_schema"]["properties"]
        assert "prompt" in defn["input_schema"]["properties"]
        assert "model" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["properties"]["action"]["enum"] == [
            "query", "auto", "compare", "models"
        ]
