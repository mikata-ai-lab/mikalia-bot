"""
image_gen.py — Generacion de imagenes para Mikalia.

Soporta multiples providers:
- Pollinations.ai (gratis, sin API key, default)
- OpenAI DALL-E 3 (mejor calidad, requiere API key)

Uso:
    from mikalia.tools.image_gen import ImageGenerationTool
    tool = ImageGenerationTool()
    result = tool.execute(prompt="A sakura tree with circuit board roots")
    # → data/images/img_1234567.png
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.image_gen")

IMAGE_DIR = Path("data/images")

PROVIDERS = {
    "pollinations": {
        "name": "Pollinations.ai",
        "description": "Gratis, sin API key, calidad buena",
        "needs_key": False,
    },
    "dalle": {
        "name": "OpenAI DALL-E 3",
        "description": "Alta calidad, requiere OPENAI_API_KEY",
        "needs_key": True,
    },
}


class ImageGenerationTool(BaseTool):
    """
    Genera imagenes a partir de texto (text-to-image).

    Default: Pollinations.ai (gratis, sin configuracion).
    Opcional: DALL-E 3 si hay OPENAI_API_KEY en .env.
    """

    @property
    def name(self) -> str:
        return "image_generation"

    @property
    def description(self) -> str:
        return (
            "Generate an image from a text description. "
            "Providers: pollinations (free, default), dalle (high quality, needs API key). "
            "Returns the path to the saved image file. "
            "Write detailed, descriptive prompts in English for best results."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Image description in English. Be specific and detailed. "
                        "Example: 'A cute anime girl with pink hair sitting at a computer, "
                        "cyberpunk style, neon lights, digital art'"
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": "Image provider (default: pollinations)",
                    "enum": list(PROVIDERS.keys()),
                },
                "size": {
                    "type": "string",
                    "description": "Image size (default: 1024x1024)",
                    "enum": ["1024x1024", "1024x1792", "1792x1024", "512x512"],
                },
            },
            "required": ["prompt"],
        }

    def execute(
        self,
        prompt: str,
        provider: str = "pollinations",
        size: str = "1024x1024",
        **_: Any,
    ) -> ToolResult:
        if not prompt.strip():
            return ToolResult(success=False, error="Prompt vacio")

        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_path = IMAGE_DIR / f"img_{timestamp}.png"

        if provider == "dalle":
            return self._generate_dalle(prompt, size, output_path)
        else:
            return self._generate_pollinations(prompt, size, output_path)

    def _generate_pollinations(
        self, prompt: str, size: str, output_path: Path,
    ) -> ToolResult:
        """Genera imagen con Pollinations.ai (gratis)."""
        width, height = size.split("x")
        encoded_prompt = quote(prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={width}&height={height}&nologo=true"
        )

        try:
            resp = requests.get(url, timeout=60, stream=True)
            resp.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = output_path.stat().st_size
            if file_size < 1000:
                return ToolResult(
                    success=False,
                    error="Imagen generada muy pequena, posible error del provider",
                )

            logger.success(f"Imagen generada: {output_path} ({file_size:,} bytes)")
            return ToolResult(
                success=True,
                output=(
                    f"Imagen generada: {output_path}\n"
                    f"Provider: Pollinations.ai (gratis)\n"
                    f"Size: {size}\n"
                    f"File: {file_size:,} bytes\n"
                    f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
                ),
            )
        except requests.Timeout:
            return ToolResult(
                success=False,
                error="Timeout generando imagen (60s). Intenta con un prompt mas simple.",
            )
        except requests.RequestException as e:
            return ToolResult(success=False, error=f"Error generando imagen: {e}")

    def _generate_dalle(
        self, prompt: str, size: str, output_path: Path,
    ) -> ToolResult:
        """Genera imagen con OpenAI DALL-E 3."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return ToolResult(
                success=False,
                error=(
                    "OPENAI_API_KEY no configurada. "
                    "Agrega tu key al .env o usa provider='pollinations' (gratis)."
                ),
            )

        # DALL-E 3 solo soporta ciertos tamanos
        valid_sizes = {"1024x1024", "1024x1792", "1792x1024"}
        if size not in valid_sizes:
            size = "1024x1024"

        url = "https://api.openai.com/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": "standard",
            "response_format": "url",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()

            data = resp.json()
            image_url = data["data"][0]["url"]
            revised_prompt = data["data"][0].get("revised_prompt", prompt)

            # Descargar la imagen
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(img_resp.content)

            file_size = output_path.stat().st_size
            logger.success(f"DALL-E imagen generada: {output_path}")
            return ToolResult(
                success=True,
                output=(
                    f"Imagen generada: {output_path}\n"
                    f"Provider: OpenAI DALL-E 3\n"
                    f"Size: {size}\n"
                    f"File: {file_size:,} bytes\n"
                    f"Prompt original: {prompt[:100]}\n"
                    f"Prompt revisado: {revised_prompt[:150]}"
                ),
            )
        except requests.RequestException as e:
            return ToolResult(success=False, error=f"Error con DALL-E: {e}")
