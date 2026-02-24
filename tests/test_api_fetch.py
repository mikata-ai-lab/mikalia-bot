"""
test_api_fetch.py — Tests para ApiFetchTool.

Verifica:
- Requests GET/POST con mocks
- Dominios bloqueados
- Auth Bearer y Basic
- Timeout y errores
- Definicion Claude correcta
- Metodos HTTP invalidos
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from mikalia.tools.api_fetch import ApiFetchTool, BLOCKED_DOMAINS, ALLOWED_METHODS


# ================================================================
# ApiFetchTool
# ================================================================

class TestApiFetchTool:

    def test_get_request_success(self):
        """GET request exitoso retorna status y body."""
        tool = ApiFetchTool()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"message": "hello"}
        mock_resp.text = '{"message": "hello"}'

        with patch("mikalia.tools.api_fetch.requests.request", return_value=mock_resp) as mock_req:
            result = tool.execute(url="https://api.example.com/data")

        assert result.success
        assert "200" in result.output
        assert "hello" in result.output
        mock_req.assert_called_once()
        call_args = mock_req.call_args
        assert call_args[0] == ("GET", "https://api.example.com/data")

    def test_post_request_with_json_body(self):
        """POST con body JSON envia json= en el request."""
        tool = ApiFetchTool()

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.reason = "Created"
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"id": 42}
        mock_resp.text = '{"id": 42}'

        with patch("mikalia.tools.api_fetch.requests.request", return_value=mock_resp) as mock_req:
            result = tool.execute(
                url="https://api.example.com/items",
                method="POST",
                body={"name": "test item"},
            )

        assert result.success
        assert "201" in result.output
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["json"] == {"name": "test item"}

    def test_blocked_domain_rejected(self):
        """Dominios bloqueados retornan error sin hacer request."""
        tool = ApiFetchTool()

        for domain in ["localhost", "127.0.0.1", "192.168.1.1", "10.0.0.5"]:
            result = tool.execute(url=f"http://{domain}/api")
            assert not result.success
            assert "bloqueado" in result.error.lower()

    def test_bearer_auth_header(self):
        """Auth bearer agrega header Authorization."""
        tool = ApiFetchTool()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {}
        mock_resp.json.return_value = {"ok": True}

        with patch("mikalia.tools.api_fetch.requests.request", return_value=mock_resp) as mock_req:
            tool.execute(
                url="https://api.example.com/secure",
                auth_type="bearer",
                auth_token="sk-test-token-123",
            )

        call_kwargs = mock_req.call_args[1]
        assert "Authorization" in call_kwargs["headers"]
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-token-123"

    def test_basic_auth_header(self):
        """Auth basic pasa tupla (user, password) a requests."""
        tool = ApiFetchTool()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_resp.headers = {}
        mock_resp.json.return_value = {"ok": True}

        with patch("mikalia.tools.api_fetch.requests.request", return_value=mock_resp) as mock_req:
            tool.execute(
                url="https://api.example.com/secure",
                auth_type="basic",
                auth_token="user:secretpass",
            )

        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["auth"] == ("user", "secretpass")

    def test_timeout_error(self):
        """Timeout retorna error con mensaje claro."""
        import requests as req

        tool = ApiFetchTool()

        with patch("mikalia.tools.api_fetch.requests.request", side_effect=req.Timeout("timed out")):
            result = tool.execute(url="https://slow-api.example.com/data")

        assert not result.success
        assert "timeout" in result.error.lower()

    def test_tool_metadata(self):
        """Tool tiene nombre, descripcion y parametros correctos."""
        tool = ApiFetchTool()

        assert tool.name == "api_fetch"
        assert "REST" in tool.description or "API" in tool.description

        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "url" in params["properties"]
        assert "method" in params["properties"]
        assert "headers" in params["properties"]
        assert "body" in params["properties"]
        assert "auth_type" in params["properties"]
        assert "url" in params["required"]

        defn = tool.to_claude_definition()
        assert defn["name"] == "api_fetch"
        assert "input_schema" in defn
        assert "description" in defn

    def test_invalid_method(self):
        """Metodo HTTP no soportado retorna error."""
        tool = ApiFetchTool()
        result = tool.execute(url="https://api.example.com/data", method="TRACE")
        assert not result.success
        assert "no soportado" in result.error.lower() or "TRACE" in result.error
