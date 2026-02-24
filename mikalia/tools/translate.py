"""
translate.py — Traduccion de texto para Mikalia.

Usa Claude API para traducciones de alta calidad.
Soporta deteccion automatica del idioma fuente.
"""

from __future__ import annotations

from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.translate")

SUPPORTED_LANGUAGES = {
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ru": "Russian",
    "ar": "Arabic",
}


class TranslateTool(BaseTool):
    """Traduce texto entre idiomas usando Claude API."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "translate"

    @property
    def description(self) -> str:
        return (
            "Translate text between languages. Auto-detects source language. "
            f"Supported: {', '.join(f'{k} ({v})' for k, v in SUPPORTED_LANGUAGES.items())}. "
            "Uses Claude for high-quality, context-aware translations."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to translate",
                },
                "target_language": {
                    "type": "string",
                    "description": "Target language code (e.g., 'en', 'es', 'ja')",
                    "enum": list(SUPPORTED_LANGUAGES.keys()),
                },
                "source_language": {
                    "type": "string",
                    "description": "Source language code (default: auto-detect)",
                },
            },
            "required": ["text", "target_language"],
        }

    def execute(
        self,
        text: str,
        target_language: str,
        source_language: str = "auto",
        **_: Any,
    ) -> ToolResult:
        if not text.strip():
            return ToolResult(success=False, error="Texto vacio")

        if target_language not in SUPPORTED_LANGUAGES:
            return ToolResult(
                success=False,
                error=f"Idioma no soportado: {target_language}. Usa: {', '.join(SUPPORTED_LANGUAGES.keys())}",
            )

        target_name = SUPPORTED_LANGUAGES[target_language]
        source_hint = ""
        if source_language != "auto" and source_language in SUPPORTED_LANGUAGES:
            source_hint = f" from {SUPPORTED_LANGUAGES[source_language]}"

        if self._client is None:
            return self._simple_translate(text, target_language, target_name)

        prompt = (
            f"Translate the following text{source_hint} to {target_name}. "
            f"Return ONLY the translation, nothing else.\n\n{text}"
        )

        try:
            response = self._client.generate(
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=len(text) * 3,
            )
            translated = response.content.strip()

            logger.success(f"Traducido a {target_name}: {len(translated)} chars")
            return ToolResult(
                success=True,
                output=(
                    f"Idioma destino: {target_name}\n"
                    f"Original ({len(text)} chars):\n{text[:200]}{'...' if len(text) > 200 else ''}\n\n"
                    f"Traduccion ({len(translated)} chars):\n{translated}"
                ),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Error traduciendo: {e}")

    def _simple_translate(
        self, text: str, target_lang: str, target_name: str,
    ) -> ToolResult:
        """Fallback sin Claude: solo reporta que no hay client."""
        return ToolResult(
            success=False,
            error="Translation requires Claude API client. Not available in standalone mode.",
        )
