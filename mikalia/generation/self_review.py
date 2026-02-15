"""
self_review.py — El lado crítico de Mikalia.

Aquí Mikalia se pone el sombrero de editora y revisa su propio trabajo.
Usa una segunda llamada a Claude con temperatura baja (0.3) para ser
más analítica y menos creativa.

¿Por qué auto-revisión?
    - Reduce errores antes de publicar
    - Asegura consistencia de tono y calidad
    - Detecta problemas que la generación inicial puede pasar por alto
    - Es más barato que publicar y corregir después

Criterios de revisión (7 puntos):
    1. ¿El título es atractivo y claro?
    2. ¿La introducción engancha al lector?
    3. ¿Hay un takeaway claro para el lector?
    4. ¿El tono es consistente con la personalidad de Mikalia?
    5. ¿La versión ES es natural (no suena a traducción robótica)?
    6. ¿Los code snippets (si hay) son correctos?
    7. ¿La longitud es apropiada (800-1500 palabras)?

Si el review no pasa, retorna sugerencias específicas para corregir.
Máximo 2 ciclos de corrección para evitar loops infinitos.

Uso:
    from mikalia.generation.self_review import SelfReviewer
    reviewer = SelfReviewer(client, config)
    result = reviewer.review(en_content, es_content)
    if result.approved:
        print("¡Post aprobado!")
    else:
        print(f"Necesita corrección: {result.suggestions}")
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mikalia.generation.client import MikaliaClient
from mikalia.config import AppConfig
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.review")


@dataclass
class ReviewResult:
    """
    Resultado de la auto-revisión de un post.

    Attributes:
        approved: Si el post pasó la revisión
        suggestions: Lista de sugerencias de mejora (vacía si aprobado)
        raw_response: Respuesta cruda de la API (para debugging)
    """
    approved: bool
    suggestions: list[str] = field(default_factory=list)
    raw_response: str = ""


class SelfReviewer:
    """
    Auto-revisor de contenido de Mikalia.

    Evalúa posts bilingües contra 7 criterios de calidad usando
    Claude con temperatura baja para máximo rigor analítico.

    Args:
        client: Cliente de la API de Claude
        config: Configuración de la app
    """

    # Prompt de revisión — define los criterios y formato de respuesta
    REVIEW_PROMPT = """You are a strict but fair blog editor. Review the following bilingual blog post.

## English Version:
{en_content}

## Spanish Version:
{es_content}

## Review Criteria:
1. Is the title engaging and clear? (no clickbait)
2. Does the introduction hook the reader in the first 2 sentences?
3. Is there a clear, useful takeaway for the reader?
4. Is the tone consistent with Mikalia's personality? (professional, warm, technical)
5. Does the Spanish version sound natural? (not robotic/Google Translate-like)
6. Are code snippets (if any) correct and relevant?
7. Is the length appropriate? (800-1500 words per language)

## Response Format:
If the post passes all criteria, respond with EXACTLY:
APPROVED

If the post needs changes, respond with EXACTLY:
NEEDS_REVISION
- [Specific suggestion 1]
- [Specific suggestion 2]
(list only the most important issues, max 4)"""

    def __init__(self, client: MikaliaClient, config: AppConfig):
        self._client = client
        self._config = config

    def review(self, en_content: str, es_content: str) -> ReviewResult:
        """
        Revisa un post bilingüe contra los criterios de calidad.

        Usa temperatura baja (0.3) para ser analítico y consistente.
        La respuesta se parsea para determinar si está aprobado o
        necesita correcciones.

        Args:
            en_content: Post en inglés (markdown sin front matter)
            es_content: Post en español (markdown sin front matter)

        Returns:
            ReviewResult con el veredicto y sugerencias.
        """
        # Construir el prompt con el contenido
        prompt = self.REVIEW_PROMPT.format(
            en_content=en_content,
            es_content=es_content,
        )

        # Llamar a la API con temperatura baja (modo analítico)
        respuesta = self._client.generate(
            user_prompt=prompt,
            temperature=self._config.mikalia.review_temperature,
            max_tokens=1024,
            system_override=(
                "You are a strict editorial reviewer. "
                "Evaluate blog post quality objectively. "
                "Be concise and specific in your feedback."
            ),
        )

        # Parsear la respuesta
        return self._parse_review(respuesta.content)

    def _parse_review(self, response: str) -> ReviewResult:
        """
        Parsea la respuesta de la API en un ReviewResult.

        La respuesta puede ser:
        - "APPROVED" → post aprobado
        - "NEEDS_REVISION\n- sugerencia 1\n- sugerencia 2" → necesita cambios

        Si la respuesta no sigue el formato esperado, se trata como
        no aprobado con un mensaje genérico (fail-safe).

        Args:
            response: Texto crudo de la respuesta de la API.

        Returns:
            ReviewResult parseado.
        """
        texto = response.strip()

        # Caso 1: Aprobado
        if texto.upper().startswith("APPROVED"):
            logger.success("Self-review: APROBADO ✓")
            return ReviewResult(
                approved=True,
                raw_response=texto,
            )

        # Caso 2: Necesita revisión
        if texto.upper().startswith("NEEDS_REVISION"):
            # Extraer sugerencias (líneas que empiezan con -)
            lineas = texto.split("\n")
            sugerencias = [
                linea.strip().lstrip("- ").strip()
                for linea in lineas
                if linea.strip().startswith("-")
            ]

            logger.warning(
                f"Self-review: NECESITA CORRECCIÓN ({len(sugerencias)} sugerencia(s))"
            )
            return ReviewResult(
                approved=False,
                suggestions=sugerencias,
                raw_response=texto,
            )

        # Caso 3: Formato inesperado (fail-safe)
        # Si Claude no sigue el formato, tratamos como no aprobado
        logger.warning("Self-review: Formato de respuesta inesperado, tratando como no aprobado")
        return ReviewResult(
            approved=False,
            suggestions=["Review response had unexpected format — manual check recommended"],
            raw_response=texto,
        )
