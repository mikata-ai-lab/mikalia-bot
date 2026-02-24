"""
api_fetch.py — Tool para llamar APIs REST.

A diferencia de web_fetch (para paginas web), este tool esta
diseñado para APIs: soporta POST/PUT/DELETE, headers custom,
auth Bearer/Basic, y body JSON o form-encoded.

Uso:
    from mikalia.tools.api_fetch import ApiFetchTool
    tool = ApiFetchTool()
    result = tool.execute(
        url="https://api.example.com/data",
        method="POST",
        headers={"X-Custom": "value"},
        body={"key": "value"},
        auth_type="bearer",
        auth_token="sk-xxx",
    )
"""

from __future__ import annotations

import json
from typing import Any

import requests

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.api_fetch")

BLOCKED_DOMAINS = [
    "localhost", "127.0.0.1", "0.0.0.0",
    "169.254.", "10.", "192.168.", "172.16.",
]

ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}


class ApiFetchTool(BaseTool):
    """Llama APIs REST con soporte completo de metodos, headers y auth."""

    @property
    def name(self) -> str:
        return "api_fetch"

    @property
    def description(self) -> str:
        return (
            "Call a REST API endpoint. Supports GET, POST, PUT, PATCH, DELETE. "
            "Can send JSON or form-encoded body, custom headers, and auth "
            "(Bearer token or Basic user:pass). Returns the response body and status code."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "API endpoint URL",
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method (default: GET)",
                    "enum": list(ALLOWED_METHODS),
                },
                "headers": {
                    "type": "object",
                    "description": "Custom headers as key-value pairs",
                },
                "body": {
                    "type": "object",
                    "description": "Request body (sent as JSON by default)",
                },
                "body_type": {
                    "type": "string",
                    "description": "Body encoding: json (default) or form",
                    "enum": ["json", "form"],
                },
                "auth_type": {
                    "type": "string",
                    "description": "Auth type: none, bearer, or basic",
                    "enum": ["none", "bearer", "basic"],
                },
                "auth_token": {
                    "type": "string",
                    "description": "Auth token (for bearer) or user:pass (for basic)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 15)",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Max response chars to return (default: 5000)",
                },
            },
            "required": ["url"],
        }

    def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        body_type: str = "json",
        auth_type: str = "none",
        auth_token: str = "",
        timeout: int = 15,
        max_chars: int = 5000,
        **_: Any,
    ) -> ToolResult:
        # Validar URL
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                success=False,
                error="URL debe empezar con http:// o https://",
            )

        for blocked in BLOCKED_DOMAINS:
            if blocked in url:
                return ToolResult(
                    success=False,
                    error=f"Dominio bloqueado por seguridad: {blocked}",
                )

        method = method.upper()
        if method not in ALLOWED_METHODS:
            return ToolResult(
                success=False,
                error=f"Metodo no soportado: {method}. Usa: {', '.join(ALLOWED_METHODS)}",
            )

        # Construir headers
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)

        # Auth
        auth = None
        if auth_type == "bearer" and auth_token:
            req_headers["Authorization"] = f"Bearer {auth_token}"
        elif auth_type == "basic" and auth_token:
            if ":" in auth_token:
                user, passwd = auth_token.split(":", 1)
                auth = (user, passwd)
            else:
                return ToolResult(
                    success=False,
                    error="Auth basic requiere formato user:password",
                )

        # Construir request kwargs
        kwargs: dict[str, Any] = {
            "headers": req_headers,
            "timeout": min(timeout, 30),
            "allow_redirects": True,
        }
        if auth:
            kwargs["auth"] = auth

        if body and method in {"POST", "PUT", "PATCH"}:
            if body_type == "form":
                kwargs["data"] = body
            else:
                kwargs["json"] = body

        logger.info(f"API {method} {url}")

        try:
            resp = requests.request(method, url, **kwargs)

            # Intentar parsear JSON
            try:
                resp_body = json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except (ValueError, json.JSONDecodeError):
                resp_body = resp.text

            truncated = resp_body[:max_chars]
            if len(resp_body) > max_chars:
                truncated += "\n...[truncado]"

            resp_headers_str = "\n".join(
                f"  {k}: {v}" for k, v in list(resp.headers.items())[:10]
            )

            return ToolResult(
                success=resp.status_code < 400,
                output=(
                    f"Status: {resp.status_code} {resp.reason}\n"
                    f"Headers:\n{resp_headers_str}\n\n"
                    f"Body:\n{truncated}"
                ),
                error=f"HTTP {resp.status_code}" if resp.status_code >= 400 else None,
            )

        except requests.Timeout:
            return ToolResult(success=False, error=f"Timeout ({timeout}s): {url}")
        except requests.RequestException as e:
            return ToolResult(success=False, error=f"Error de conexion: {e}")
