"""
rss_reader.py — Lector de RSS feeds para Mikalia.

Parsea feeds RSS/Atom usando solo stdlib (xml.etree).
Sin dependencias externas.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import requests

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.rss_reader")

MAX_ITEMS = 10


class RssFeedTool(BaseTool):
    """Lee y resume feeds RSS/Atom."""

    @property
    def name(self) -> str:
        return "rss_feed"

    @property
    def description(self) -> str:
        return (
            "Read RSS/Atom feeds. Provide a feed URL and get the latest articles. "
            "Returns titles, dates, and summaries. "
            "Useful for staying updated on tech blogs, news, and podcasts."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "RSS/Atom feed URL",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max items to return (default: 5, max: 10)",
                },
            },
            "required": ["url"],
        }

    def execute(
        self, url: str, limit: int = 5, **_: Any
    ) -> ToolResult:
        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, error="URL invalida")

        limit = min(max(limit, 1), MAX_ITEMS)

        try:
            headers = {"User-Agent": "MikaliaBot/1.0"}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            items = self._parse_rss(root) or self._parse_atom(root)

            if not items:
                return ToolResult(
                    success=False,
                    error="No se encontraron articulos en el feed",
                )

            items = items[:limit]
            lines = [f"Feed: {url}", f"Articulos: {len(items)}", ""]

            for i, item in enumerate(items, 1):
                lines.append(f"{i}. {item['title']}")
                if item.get("date"):
                    lines.append(f"   Fecha: {item['date']}")
                if item.get("link"):
                    lines.append(f"   Link: {item['link']}")
                if item.get("summary"):
                    summary = item["summary"][:150]
                    lines.append(f"   {summary}...")
                lines.append("")

            logger.success(f"Feed leido: {len(items)} articulos de {url}")
            return ToolResult(success=True, output="\n".join(lines))

        except ET.ParseError:
            return ToolResult(success=False, error="Error parseando XML del feed")
        except requests.Timeout:
            return ToolResult(success=False, error="Timeout descargando feed")
        except requests.RequestException as e:
            return ToolResult(success=False, error=f"Error descargando feed: {e}")

    def _parse_rss(self, root: ET.Element) -> list[dict]:
        """Parsea formato RSS 2.0."""
        items = []
        # RSS 2.0: channel > item
        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item"):
            items.append({
                "title": self._text(item, "title"),
                "link": self._text(item, "link"),
                "date": self._text(item, "pubDate"),
                "summary": self._clean_html(self._text(item, "description")),
            })
        return items

    def _parse_atom(self, root: ET.Element) -> list[dict]:
        """Parsea formato Atom."""
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []

        for entry in root.findall("atom:entry", ns):
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""

            items.append({
                "title": self._text_ns(entry, "atom:title", ns),
                "link": link,
                "date": self._text_ns(entry, "atom:updated", ns)
                    or self._text_ns(entry, "atom:published", ns),
                "summary": self._clean_html(
                    self._text_ns(entry, "atom:summary", ns)
                    or self._text_ns(entry, "atom:content", ns)
                ),
            })
        return items

    def _text(self, el: ET.Element, tag: str) -> str:
        """Extrae texto de un subelemento."""
        child = el.find(tag)
        return child.text.strip() if child is not None and child.text else ""

    def _text_ns(self, el: ET.Element, tag: str, ns: dict) -> str:
        """Extrae texto con namespace."""
        child = el.find(tag, ns)
        return child.text.strip() if child is not None and child.text else ""

    def _clean_html(self, text: str) -> str:
        """Remueve tags HTML basicos."""
        import re
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
