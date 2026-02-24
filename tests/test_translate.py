"""
test_translate.py — Tests para TranslateTool.

Verifica:
- Traduccion con cliente Claude (mock)
- Fallback sin cliente retorna error
- Idioma no soportado
- Texto vacio
- Definicion Claude correcta
- Mismo idioma fuente y destino
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from mikalia.tools.translate import TranslateTool, SUPPORTED_LANGUAGES


# ================================================================
# TranslateTool
# ================================================================

class TestTranslateTool:

    def test_translate_with_client(self):
        """Traduccion exitosa con cliente Claude mock."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Hello, how are you?"
        mock_client.generate.return_value = mock_response

        tool = TranslateTool(client=mock_client)
        result = tool.execute(text="Hola, como estas?", target_language="en")

        assert result.success
        assert "Hello, how are you?" in result.output
        assert "English" in result.output
        mock_client.generate.assert_called_once()
        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs["temperature"] == 0.3

    def test_translate_without_client_returns_error(self):
        """Sin cliente Claude retorna error de standalone mode."""
        tool = TranslateTool(client=None)
        result = tool.execute(text="Hola mundo", target_language="en")

        assert not result.success
        assert "client" in result.error.lower() or "standalone" in result.error.lower()

    def test_unsupported_language(self):
        """Idioma no soportado retorna error con lista de idiomas."""
        tool = TranslateTool()
        result = tool.execute(text="Hello", target_language="xx")

        assert not result.success
        assert "no soportado" in result.error.lower() or "xx" in result.error

    def test_empty_text_error(self):
        """Texto vacio retorna error."""
        tool = TranslateTool()
        result = tool.execute(text="   ", target_language="en")

        assert not result.success
        assert "vacio" in result.error.lower()

    def test_tool_metadata(self):
        """Tool tiene nombre, descripcion y parametros correctos."""
        tool = TranslateTool()

        assert tool.name == "translate"
        assert "translate" in tool.description.lower() or "Translate" in tool.description

        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "text" in params["properties"]
        assert "target_language" in params["properties"]
        assert "source_language" in params["properties"]
        assert "text" in params["required"]
        assert "target_language" in params["required"]

        defn = tool.to_claude_definition()
        assert defn["name"] == "translate"
        assert "input_schema" in defn

    def test_same_source_target_language(self):
        """Traduccion del mismo idioma fuente a destino funciona sin error especial."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Hola mundo"
        mock_client.generate.return_value = mock_response

        tool = TranslateTool(client=mock_client)
        result = tool.execute(
            text="Hola mundo",
            target_language="es",
            source_language="es",
        )

        assert result.success
        assert "Spanish" in result.output
        # El prompt incluye "from Spanish"
        call_kwargs = mock_client.generate.call_args[1]
        assert "Spanish" in call_kwargs["user_prompt"]
