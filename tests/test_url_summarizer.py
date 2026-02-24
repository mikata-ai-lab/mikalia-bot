"""
test_url_summarizer.py — Tests para UrlSummarizerTool.

Verifica:
- Resumen con cliente AI (mock)
- Resumen basico sin cliente
- Deteccion de YouTube URLs
- Validacion de URL
- Manejo de timeout
- Contenido vacio
- Definiciones Claude correctas
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mikalia.tools.url_summarizer import UrlSummarizerTool


# ================================================================
# Helpers
# ================================================================

SAMPLE_HTML = (
    "<html><head><title>Test Page</title>"
    '<meta name="description" content="A test description">'
    "</head><body>"
    "<h1>Main heading</h1>"
    "<p>This is a paragraph with enough content to pass the minimum length check. "
    "It contains multiple sentences about various topics. "
    "The content is interesting and informative for testing purposes.</p>"
    "</body></html>"
)

EMPTY_HTML = "<html><body></body></html>"


def _mock_response(text=SAMPLE_HTML, status_code=200):
    """Crea un mock de requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ================================================================
# UrlSummarizerTool — summarization
# ================================================================

class TestUrlSummarizer:
    @patch("mikalia.tools.url_summarizer.requests.get")
    def test_summarize_with_client(self, mock_get):
        """Con cliente AI, usa _summarize_with_ai."""
        mock_get.return_value = _mock_response()
        mock_client = MagicMock()
        mock_client.generate.return_value = "Este articulo trata sobre testing."

        tool = UrlSummarizerTool(client=mock_client)
        result = tool.execute(url="https://example.com/article")

        assert result.success
        assert "Este articulo trata sobre testing" in result.output
        assert "Web" in result.output
        mock_client.generate.assert_called_once()

    @patch("mikalia.tools.url_summarizer.requests.get")
    def test_summarize_without_client_uses_basic(self, mock_get):
        """Sin cliente AI, usa resumen basico (primeras oraciones)."""
        mock_get.return_value = _mock_response()

        tool = UrlSummarizerTool(client=None)
        result = tool.execute(url="https://example.com/article")

        assert result.success
        assert "Resumen" in result.output
        assert "https://example.com/article" in result.output


# ================================================================
# UrlSummarizerTool — YouTube detection
# ================================================================

class TestUrlYouTube:
    @patch("mikalia.tools.url_summarizer.requests.get")
    def test_youtube_url_detected(self, mock_get):
        """URLs de YouTube se detectan correctamente."""
        mock_get.return_value = _mock_response()

        tool = UrlSummarizerTool(client=None)
        result = tool.execute(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        assert result.success
        assert "YouTube" in result.output

    @patch("mikalia.tools.url_summarizer.requests.get")
    def test_youtube_short_url_detected(self, mock_get):
        """URLs cortas de YouTube se detectan."""
        mock_get.return_value = _mock_response()

        tool = UrlSummarizerTool(client=None)
        result = tool.execute(url="https://youtu.be/dQw4w9WgXcQ")

        assert result.success
        assert "YouTube" in result.output


# ================================================================
# UrlSummarizerTool — error handling
# ================================================================

class TestUrlErrors:
    def test_invalid_url(self):
        """URL sin http/https retorna error."""
        tool = UrlSummarizerTool()
        result = tool.execute(url="ftp://example.com")

        assert not result.success
        assert "http" in result.error.lower()

    def test_invalid_url_no_protocol(self):
        """URL sin protocolo retorna error."""
        tool = UrlSummarizerTool()
        result = tool.execute(url="example.com")

        assert not result.success
        assert "http" in result.error.lower()

    @patch("mikalia.tools.url_summarizer.requests.get")
    def test_timeout_error(self, mock_get):
        """Timeout retorna error descriptivo."""
        import requests as req
        mock_get.side_effect = req.Timeout("Connection timed out")

        tool = UrlSummarizerTool()
        result = tool.execute(url="https://slow-site.com")

        assert not result.success
        assert "Timeout" in result.error

    @patch("mikalia.tools.url_summarizer.requests.get")
    def test_empty_content(self, mock_get):
        """Contenido vacio o muy corto retorna error."""
        mock_get.return_value = _mock_response(text=EMPTY_HTML)

        tool = UrlSummarizerTool()
        result = tool.execute(url="https://example.com/empty")

        assert not result.success
        assert "contenido" in result.error.lower()


# ================================================================
# UrlSummarizerTool — metadata
# ================================================================

class TestUrlMetadata:
    def test_tool_metadata(self):
        """Definicion Claude tiene formato correcto."""
        tool = UrlSummarizerTool()
        assert tool.name == "url_summarizer"
        assert "url" in tool.description.lower() or "summarize" in tool.description.lower()

        d = tool.to_claude_definition()
        assert d["name"] == "url_summarizer"
        assert "url" in d["input_schema"]["properties"]
        assert "language" in d["input_schema"]["properties"]
        assert "url" in d["input_schema"]["required"]
