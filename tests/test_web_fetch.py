"""
test_web_fetch.py — Tests para WebFetchTool.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from mikalia.tools.web_fetch import WebFetchTool, _strip_html, BLOCKED_DOMAINS


# ================================================================
# _strip_html
# ================================================================

class TestStripHtml:
    def test_removes_script_tags(self):
        html = '<p>Hello</p><script>alert("xss")</script><p>World</p>'
        result = _strip_html(html)
        assert "alert" not in result
        assert "Hello" in result
        assert "World" in result

    def test_removes_style_tags(self):
        html = '<style>.body{color:red}</style><p>Content</p>'
        result = _strip_html(html)
        assert "color" not in result
        assert "Content" in result

    def test_removes_html_tags(self):
        html = '<div class="main"><h1>Title</h1><p>Text</p></div>'
        result = _strip_html(html)
        assert "<" not in result
        assert "Title" in result
        assert "Text" in result

    def test_collapses_whitespace(self):
        html = '<p>  Hello   World  </p>'
        result = _strip_html(html)
        assert "  " not in result


# ================================================================
# WebFetchTool
# ================================================================

class TestWebFetchTool:
    def test_name(self):
        tool = WebFetchTool()
        assert tool.name == "web_fetch"

    def test_claude_definition(self):
        tool = WebFetchTool()
        d = tool.to_claude_definition()
        assert d["name"] == "web_fetch"
        assert "url" in d["input_schema"]["properties"]
        assert "max_chars" in d["input_schema"]["properties"]

    def test_rejects_non_http_url(self):
        tool = WebFetchTool()
        result = tool.execute(url="ftp://example.com")
        assert not result.success
        assert "http" in result.error.lower()

    def test_rejects_file_url(self):
        tool = WebFetchTool()
        result = tool.execute(url="file:///etc/passwd")
        assert not result.success

    def test_blocks_localhost(self):
        tool = WebFetchTool()
        result = tool.execute(url="http://localhost:8080/api")
        assert not result.success
        assert "bloqueado" in result.error.lower()

    def test_blocks_internal_ips(self):
        tool = WebFetchTool()
        for ip in ["127.0.0.1", "192.168.1.1", "10.0.0.1"]:
            result = tool.execute(url=f"http://{ip}/secret")
            assert not result.success, f"Should block {ip}"

    @patch("mikalia.tools.web_fetch.requests.get")
    def test_fetch_html_strips_tags(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.text = "<html><body><h1>Hello</h1><p>World</p></body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = WebFetchTool()
        result = tool.execute(url="https://example.com")
        assert result.success
        assert "Hello" in result.output
        assert "<h1>" not in result.output

    @patch("mikalia.tools.web_fetch.requests.get")
    def test_fetch_json_returns_raw(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = '{"key": "value"}'
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = WebFetchTool()
        result = tool.execute(url="https://api.example.com/data")
        assert result.success
        assert '"key"' in result.output

    @patch("mikalia.tools.web_fetch.requests.get")
    def test_respects_max_chars(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.text = "A" * 10000
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        tool = WebFetchTool()
        result = tool.execute(url="https://example.com", max_chars=100)
        assert result.success
        # Output includes "[200] url\n\n" prefix + max_chars of content
        content_part = result.output.split("\n\n", 1)[1]
        assert len(content_part) <= 100

    @patch("mikalia.tools.web_fetch.requests.get")
    def test_handles_timeout(self, mock_get):
        import requests as req
        mock_get.side_effect = req.Timeout("Connection timed out")

        tool = WebFetchTool()
        result = tool.execute(url="https://slow-site.com")
        assert not result.success
        assert "timeout" in result.error.lower()

    @patch("mikalia.tools.web_fetch.requests.get")
    def test_handles_http_error(self, mock_get):
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = req.HTTPError(response=mock_resp)
        mock_get.side_effect = error

        tool = WebFetchTool()
        result = tool.execute(url="https://example.com/missing")
        assert not result.success
        assert "404" in result.error
