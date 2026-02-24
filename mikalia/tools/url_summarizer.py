"""
url_summarizer.py — Resume contenido de URLs para Mikalia.

Descarga paginas web o transcripciones de YouTube
y genera resumenes con Claude.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.url_summarizer")

MAX_CONTENT_LENGTH = 15000


class UrlSummarizerTool(BaseTool):
    """Resume contenido de URLs y videos de YouTube."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "url_summarizer"

    @property
    def description(self) -> str:
        return (
            "Summarize content from a URL or YouTube video. "
            "Fetches the page content, extracts text, and generates "
            "a concise summary. For YouTube, extracts video info. "
            "Supports any public URL."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to summarize",
                },
                "language": {
                    "type": "string",
                    "description": "Summary language (default: es)",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Max summary words (default: 200)",
                },
            },
            "required": ["url"],
        }

    def execute(
        self,
        url: str,
        language: str = "es",
        max_length: int = 200,
        **_: Any,
    ) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, error="URL debe empezar con http:// o https://")

        try:
            is_youtube = self._is_youtube(url)
            content = self._fetch_content(url)

            if not content or len(content.strip()) < 50:
                return ToolResult(
                    success=False,
                    error="No se pudo extraer suficiente contenido de la URL",
                )

            # Truncar contenido
            if len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "\n...[truncado]"

            # Generar resumen
            if self._client:
                summary = self._summarize_with_ai(content, language, max_length, is_youtube)
            else:
                summary = self._basic_summary(content)

            source = "YouTube" if is_youtube else "Web"
            return ToolResult(
                success=True,
                output=f"Resumen ({source}):\n{summary}\n\nFuente: {url}",
            )

        except requests.Timeout:
            return ToolResult(success=False, error="Timeout descargando URL")
        except requests.RequestException as e:
            return ToolResult(success=False, error=f"Error descargando URL: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"Error resumiendo: {e}")

    def _is_youtube(self, url: str) -> bool:
        """Detecta si es un video de YouTube."""
        return bool(re.search(
            r"(youtube\.com/watch|youtu\.be/|youtube\.com/shorts/)", url
        ))

    def _fetch_content(self, url: str) -> str:
        """Descarga y extrae texto de una URL."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; MikaliaBot/1.0)"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        html = resp.text

        # Remover scripts y styles
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        # Extraer titulo
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Extraer meta description
        meta_match = re.search(
            r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']',
            html, re.IGNORECASE
        )
        description = meta_match.group(1).strip() if meta_match else ""

        # Remover tags HTML
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        parts = []
        if title:
            parts.append(f"Titulo: {title}")
        if description:
            parts.append(f"Descripcion: {description}")
        parts.append(f"\nContenido:\n{text[:MAX_CONTENT_LENGTH]}")

        return "\n".join(parts)

    def _summarize_with_ai(
        self, content: str, language: str, max_length: int, is_youtube: bool
    ) -> str:
        """Resume usando Claude."""
        source_type = "video de YouTube" if is_youtube else "pagina web"
        prompt = (
            f"Resume el siguiente contenido de {source_type} en {language}. "
            f"Maximo {max_length} palabras. Se conciso y captura los puntos clave:\n\n"
            f"{content}"
        )

        try:
            response = self._client.generate(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
            return response
        except Exception as e:
            logger.warning(f"AI summary failed, using basic: {e}")
            return self._basic_summary(content)

    def _basic_summary(self, content: str) -> str:
        """Resumen basico sin AI: primeras oraciones."""
        sentences = re.split(r"[.!?]+", content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        return ". ".join(sentences[:5]) + "."
