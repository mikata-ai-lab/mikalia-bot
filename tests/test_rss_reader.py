"""
test_rss_reader.py — Tests para RssFeedTool.

Verifica:
- Parseo de RSS 2.0
- Parseo de Atom
- URL invalida
- Feed vacio
- Limite de items
- Timeout
- Definiciones Claude correctas
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mikalia.tools.rss_reader import RssFeedTool


# ================================================================
# Sample feeds
# ================================================================

SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Blog</title>
    <link>http://example.com</link>
    <description>A test RSS feed</description>
    <item>
      <title>Article 1</title>
      <link>http://example.com/1</link>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
      <description>Summary of article 1</description>
    </item>
    <item>
      <title>Article 2</title>
      <link>http://example.com/2</link>
      <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
      <description>Summary of article 2</description>
    </item>
    <item>
      <title>Article 3</title>
      <link>http://example.com/3</link>
      <pubDate>Wed, 03 Jan 2024 00:00:00 GMT</pubDate>
      <description>Summary of article 3</description>
    </item>
  </channel>
</rss>"""

SAMPLE_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <link href="http://example.com"/>
  <entry>
    <title>Atom Entry 1</title>
    <link href="http://example.com/atom/1"/>
    <updated>2024-01-01T00:00:00Z</updated>
    <summary>Atom summary 1</summary>
  </entry>
  <entry>
    <title>Atom Entry 2</title>
    <link href="http://example.com/atom/2"/>
    <updated>2024-01-02T00:00:00Z</updated>
    <summary>Atom summary 2</summary>
  </entry>
</feed>"""

EMPTY_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Feed</title>
    <link>http://example.com</link>
    <description>No items here</description>
  </channel>
</rss>"""


def _mock_response(content, status_code=200):
    """Crea un mock de requests.Response con content bytes."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = content.encode("utf-8")
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ================================================================
# RssFeedTool — RSS parsing
# ================================================================

class TestRssFeedParsing:
    @patch("mikalia.tools.rss_reader.requests.get")
    def test_parse_rss_feed(self, mock_get):
        """Parsea feed RSS 2.0 correctamente."""
        mock_get.return_value = _mock_response(SAMPLE_RSS)

        tool = RssFeedTool()
        result = tool.execute(url="https://example.com/feed.xml")

        assert result.success
        assert "Article 1" in result.output
        assert "Article 2" in result.output
        assert "http://example.com/1" in result.output
        assert "Summary of article 1" in result.output

    @patch("mikalia.tools.rss_reader.requests.get")
    def test_parse_atom_feed(self, mock_get):
        """Parsea feed Atom correctamente."""
        mock_get.return_value = _mock_response(SAMPLE_ATOM)

        tool = RssFeedTool()
        result = tool.execute(url="https://example.com/atom.xml")

        assert result.success
        assert "Atom Entry 1" in result.output
        assert "Atom Entry 2" in result.output
        assert "Atom summary 1" in result.output

    @patch("mikalia.tools.rss_reader.requests.get")
    def test_rss_includes_dates(self, mock_get):
        """Los items del feed incluyen fechas."""
        mock_get.return_value = _mock_response(SAMPLE_RSS)

        tool = RssFeedTool()
        result = tool.execute(url="https://example.com/feed.xml")

        assert result.success
        assert "Fecha:" in result.output


# ================================================================
# RssFeedTool — limits and filtering
# ================================================================

class TestRssFeedLimits:
    @patch("mikalia.tools.rss_reader.requests.get")
    def test_limit_items(self, mock_get):
        """Limitar numero de items funciona."""
        mock_get.return_value = _mock_response(SAMPLE_RSS)

        tool = RssFeedTool()
        result = tool.execute(url="https://example.com/feed.xml", limit=1)

        assert result.success
        assert "Article 1" in result.output
        assert "Articulos: 1" in result.output

    @patch("mikalia.tools.rss_reader.requests.get")
    def test_default_limit_five(self, mock_get):
        """Limite por defecto es 5 items."""
        mock_get.return_value = _mock_response(SAMPLE_RSS)

        tool = RssFeedTool()
        result = tool.execute(url="https://example.com/feed.xml")

        assert result.success
        # Solo 3 items en el sample, todos se muestran
        assert "Articulos: 3" in result.output


# ================================================================
# RssFeedTool — error handling
# ================================================================

class TestRssFeedErrors:
    def test_invalid_url(self):
        """URL sin http/https retorna error."""
        tool = RssFeedTool()
        result = tool.execute(url="ftp://example.com/feed.xml")

        assert not result.success
        assert "invalida" in result.error.lower()

    def test_invalid_url_no_protocol(self):
        """URL sin protocolo retorna error."""
        tool = RssFeedTool()
        result = tool.execute(url="example.com/feed.xml")

        assert not result.success
        assert "invalida" in result.error.lower()

    @patch("mikalia.tools.rss_reader.requests.get")
    def test_empty_feed(self, mock_get):
        """Feed sin items retorna error."""
        mock_get.return_value = _mock_response(EMPTY_RSS)

        tool = RssFeedTool()
        result = tool.execute(url="https://example.com/empty.xml")

        assert not result.success
        assert "No se encontraron" in result.error

    @patch("mikalia.tools.rss_reader.requests.get")
    def test_timeout_error(self, mock_get):
        """Timeout retorna error descriptivo."""
        import requests as req
        mock_get.side_effect = req.Timeout("Connection timed out")

        tool = RssFeedTool()
        result = tool.execute(url="https://slow-feed.com/rss")

        assert not result.success
        assert "Timeout" in result.error

    @patch("mikalia.tools.rss_reader.requests.get")
    def test_invalid_xml(self, mock_get):
        """XML invalido retorna error de parseo."""
        mock_get.return_value = _mock_response("this is not xml at all <><>")

        tool = RssFeedTool()
        result = tool.execute(url="https://example.com/broken.xml")

        assert not result.success
        assert "parsea" in result.error.lower() or "XML" in result.error


# ================================================================
# RssFeedTool — metadata
# ================================================================

class TestRssFeedMetadata:
    def test_tool_metadata(self):
        """Definicion Claude tiene formato correcto."""
        tool = RssFeedTool()
        assert tool.name == "rss_feed"
        assert "rss" in tool.description.lower() or "feed" in tool.description.lower()

        d = tool.to_claude_definition()
        assert d["name"] == "rss_feed"
        assert "url" in d["input_schema"]["properties"]
        assert "limit" in d["input_schema"]["properties"]
        assert "url" in d["input_schema"]["required"]
