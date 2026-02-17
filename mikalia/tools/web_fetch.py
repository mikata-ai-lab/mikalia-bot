"""
web_fetch.py — Tool para que Mikalia busque informacion en la web.

Usa requests para obtener contenido de URLs.
Extrae texto limpio de HTML para analisis.

Uso:
    from mikalia.tools.web_fetch import WebFetchTool
    tool = WebFetchTool()
    result = tool.execute(url="https://example.com")
"""

from __future__ import annotations

import re
from typing import Any

import requests

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.web_fetch")

# Dominios bloqueados por seguridad
BLOCKED_DOMAINS = [
    "localhost", "127.0.0.1", "0.0.0.0",
    "169.254.", "10.", "192.168.", "172.16.",
]


def _strip_html(html: str) -> str:
    """Extrae texto limpio de HTML."""
    # Quitar scripts y styles
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    # Quitar tags HTML
    text = re.sub(r"<[^>]+>", " ", text)
    # Limpiar whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


class WebFetchTool(BaseTool):
    """Obtiene contenido de una URL."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch content from a URL and return the text. "
            "Use this to look up documentation, read web pages, "
            "or get information from the internet. "
            "Returns plain text extracted from HTML."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return",
                    "default": 5000,
                },
            },
            "required": ["url"],
        }

    def execute(
        self, url: str, max_chars: int = 5000, **_: Any
    ) -> ToolResult:
        # Validar URL
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                success=False,
                error="URL debe empezar con http:// o https://",
            )

        # Bloquear dominios internos
        for blocked in BLOCKED_DOMAINS:
            if blocked in url:
                return ToolResult(
                    success=False,
                    error=f"Dominio bloqueado por seguridad: {blocked}",
                )

        logger.info(f"Fetching: {url}")

        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/json",
                    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
                },
                allow_redirects=True,
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")

            if "json" in content_type:
                text = resp.text[:max_chars]
            elif "html" in content_type:
                text = _strip_html(resp.text)[:max_chars]
            else:
                text = resp.text[:max_chars]

            return ToolResult(
                success=True,
                output=f"[{resp.status_code}] {url}\n\n{text}",
            )

        except requests.Timeout:
            return ToolResult(success=False, error=f"Timeout al fetchar {url}")
        except requests.HTTPError as e:
            return ToolResult(
                success=False,
                error=f"HTTP error {e.response.status_code}: {url}",
            )
        except requests.RequestException as e:
            return ToolResult(success=False, error=f"Error de conexion: {e}")
