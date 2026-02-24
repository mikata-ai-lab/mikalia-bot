"""
post_generator.py — El corazón creativo de Mikalia.

Este archivo orquesta la generación completa de un post bilingüe.
Es el módulo más importante para F1 porque maneja todo el flujo:

    1. Genera post en inglés (idioma base)
    2. Adapta a español (NO traduce literalmente)
    3. Genera metadata (título, descripción, tags) con llamadas enfocadas
    4. Auto-revisa calidad con self_review
    5. Si no pasa review, corrige (máximo 2 iteraciones)
    6. Retorna ambas versiones listas para Hugo

¿Por qué EN primero?
    El blog tiene audiencia internacional y es más fácil adaptar
    EN→ES que al revés manteniendo calidad técnica.

¿Por qué "adaptar" y no "traducir"?
    Mikalia tiene personalidad en AMBOS idiomas. El post en español
    puede usar expresiones diferentes, ejemplos culturalmente
    relevantes, y un tono ligeramente distinto. Debe leerse como
    si fue escrito originalmente en español.

¿Por qué llamadas separadas para metadata?
    Prompts enfocados producen mejores resultados que pedir todo junto.
    Un prompt que solo genera un título produce títulos más creativos
    que uno que genera título + descripción + tags + contenido.

Uso:
    from mikalia.generation.post_generator import PostGenerator
    generator = PostGenerator(client=client, config=config)
    result = generator.generate_post("Building autonomous AI agents")
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from mikalia.generation.client import MikaliaClient
from mikalia.generation.self_review import SelfReviewer
from mikalia.config import AppConfig
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.generation")

# Timezone de Monterrey (CST = UTC-6)
CST = timezone(timedelta(hours=-6))


@dataclass
class PostMetadata:
    """
    Metadata de un post generado.

    Estos valores se usan para construir el front matter de Hugo
    y para nombrar los archivos/directorios.
    """
    title_en: str
    title_es: str
    description_en: str
    description_es: str
    tags: list[str]
    category: str
    slug: str
    date: str  # Formato ISO 8601 con timezone


@dataclass
class GeneratedPost:
    """
    Resultado completo de la generación de un post bilingüe.

    Contiene todo lo necesario para que hugo_formatter cree
    los archivos markdown y git_ops los publique.
    """
    content_en: str
    content_es: str
    metadata: PostMetadata
    review_passed: bool = False
    review_iterations: int = 0


class PostGenerator:
    """
    Generador de posts bilingües para el blog de Mikalia.

    Orquesta el flujo completo: generación EN → adaptación ES →
    metadata → self-review → corrección si necesario.

    Args:
        client: Cliente de la API de Claude (MikaliaClient)
        config: Configuración de la app (AppConfig)
    """

    def __init__(self, client: MikaliaClient, config: AppConfig):
        self._client = client
        self._config = config
        self._reviewer = SelfReviewer(client, config)

    def generate_post(
        self,
        topic: str,
        category: str | None = None,
        tags: list[str] | None = None,
        context: str | None = None,
    ) -> GeneratedPost:
        """
        Genera un post bilingüe completo sobre el tema dado.

        Este es el método principal que orquesta todo el flujo.
        Cada paso es una llamada separada a la API por diseño
        (prompts enfocados = mejores resultados).

        Args:
            topic: Tema del post (ej: "Building AI agents with Python")
            category: Categoría opcional (ej: "ai", "tutorials")
            tags: Tags opcionales (si no se dan, se generan automáticamente)
            context: Contexto adicional de un repo o documento [F2]

        Returns:
            GeneratedPost con contenido EN/ES, metadata, y estado de review.
        """
        logger.mikalia(f"¡Vamos a escribir sobre: {topic}!")

        # === PASO 1: Generar post en inglés ===
        logger.step(1, 6, "Generando post en inglés...")
        content_en = self._generate_en(topic, context)

        # === PASO 2: Adaptar a español ===
        logger.step(2, 6, "Adaptando al español...")
        content_es = self._adapt_es(content_en, topic)

        # === PASO 3: Generar metadata ===
        logger.step(3, 6, "Generando metadata (título, descripción, tags)...")
        metadata = self._generate_metadata(content_en, topic, category, tags)

        # === PASO 4: Self-review ===
        logger.step(4, 6, "Auto-revisando calidad...")
        post = GeneratedPost(
            content_en=content_en,
            content_es=content_es,
            metadata=metadata,
        )

        # === PASO 5: Ciclo de corrección ===
        post = self._run_review_cycle(post, topic, context)

        # === PASO 6: Resultado ===
        if post.review_passed:
            logger.success(
                f"Post aprobado después de {post.review_iterations} revisión(es)"
            )
        else:
            logger.warning(
                "Post no pasó review después del máximo de iteraciones. "
                "Se publica con advertencia."
            )

        return post

    def _generate_en(self, topic: str, context: str | None = None) -> str:
        """
        Genera el cuerpo del post en inglés.

        Esta es la primera llamada a la API. Le damos a Claude:
        - El system prompt de MIKALIA.md (personalidad)
        - El tema y estructura deseada
        - Contexto adicional si viene de un repo/documento [F2]

        Args:
            topic: Tema del post.
            context: Contexto de repo/documento (opcional).

        Returns:
            Contenido markdown del post en inglés (sin front matter).
        """
        prompt = f"""Write a blog post about: {topic}

Instructions:
- Write in English, in Mikalia's voice (first person)
- Structure: engaging intro, clear sections with ## headings, code if relevant, conclusion with takeaway
- Length: 800-1500 words
- Include practical examples, not just theory
- End with the signature: *— Mikalia 🌸*
- Do NOT include front matter (title, date, etc.) — only the body content
- Do NOT include a # title heading — the title comes from front matter"""

        # Si hay contexto de un repo o documento, agregarlo
        if context:
            prompt += f"\n\nAdditional context to inform the post:\n{context}"

        respuesta = self._client.generate(
            user_prompt=prompt,
            temperature=self._config.mikalia.generation_temperature,
            max_tokens=self._config.mikalia.max_tokens,
        )

        return respuesta.content

    def _adapt_es(self, en_content: str, topic: str) -> str:
        """
        Adapta el post al español (NO traducción literal).

        La clave aquí es la instrucción explícita de ADAPTAR, no TRADUCIR.
        Mikalia en español puede usar:
        - Expresiones y modismos naturales en español
        - Ejemplos culturalmente relevantes
        - Un tono ligeramente diferente (más cálido, más cercano)

        El resultado debe leerse como si fue escrito originalmente en español.

        Args:
            en_content: Contenido en inglés a adaptar.
            topic: Tema original (para contexto).

        Returns:
            Contenido markdown del post en español.
        """
        prompt = f"""Adapt the following blog post to Spanish.

IMPORTANT: This is NOT a literal translation. You are Mikalia writing in Spanish.
- Adapt idioms and expressions so they feel natural in Spanish
- Keep the same structure and technical accuracy
- The Spanish version should read as if it was originally written in Spanish
- Maintain the same tone but feel free to adjust cultural references
- Keep code snippets in English (code is universal)
- Keep the signature: *— Mikalia 🌸*

English post to adapt:

{en_content}"""

        respuesta = self._client.generate(
            user_prompt=prompt,
            temperature=self._config.mikalia.generation_temperature,
            max_tokens=self._config.mikalia.max_tokens,
        )

        return respuesta.content

    def _generate_metadata(
        self,
        content_en: str,
        topic: str,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> PostMetadata:
        """
        Genera metadata del post con llamadas enfocadas.

        Cada pieza de metadata (título, descripción, tags) se genera
        con una llamada separada y enfocada a la API. Esto produce
        resultados significativamente mejores que pedirlo todo junto.

        Args:
            content_en: Contenido del post (para contexto)
            topic: Tema original
            category: Categoría (si no se da, se infiere)
            tags: Tags (si no se dan, se generan)

        Returns:
            PostMetadata con todos los campos listos para Hugo.
        """
        # Generar todo en una sola llamada JSON para eficiencia
        prompt = f"""Based on this blog post content, generate metadata in JSON format.

Post topic: {topic}
Post content (first 500 chars): {content_en[:500]}...

Generate a JSON response with exactly these fields:
{{
    "title_en": "Engaging title in English (max 70 chars, no clickbait)",
    "title_es": "Título atractivo en español (max 70 chars)",
    "description_en": "SEO-friendly description in English (max 160 chars)",
    "description_es": "Descripción SEO en español (max 160 chars)",
    "tags": ["tag1", "tag2", "tag3"],
    "category": "category-name",
    "slug": "seo-friendly-url-slug"
}}

Rules:
- Title: concise, engaging, no clickbait, reflects the actual content
- Description: 1-2 sentences, informative, SEO-optimized
- Tags: 3-5 lowercase tags relevant to the content
- Category: one of {self._config.blog.categories}
- Slug: lowercase, hyphens, no special chars, max 50 chars
- Respond ONLY with valid JSON, no markdown code fences"""

        respuesta = self._client.generate(
            user_prompt=prompt,
            temperature=0.3,  # Baja para metadata precisa
            max_tokens=512,
        )

        # Parsear JSON de la respuesta
        try:
            # Intentar limpiar la respuesta si tiene code fences
            texto = respuesta.content.strip()
            if texto.startswith("```"):
                texto = texto.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            datos = json.loads(texto)
        except json.JSONDecodeError:
            # Si falla el parseo, usar valores por defecto
            logger.warning("No se pudo parsear metadata JSON, usando defaults")
            slug = topic.lower().replace(" ", "-")[:50]
            datos = {
                "title_en": topic,
                "title_es": topic,
                "description_en": f"A post about {topic}",
                "description_es": f"Un post sobre {topic}",
                "tags": ["ai", "blog"],
                "category": "ai",
                "slug": slug,
            }

        # Sobrescribir con valores proporcionados por el usuario
        if category:
            datos["category"] = category
        if tags:
            datos["tags"] = tags

        # Generar fecha actual en timezone de Monterrey
        ahora = datetime.now(CST)
        fecha_iso = ahora.strftime("%Y-%m-%dT%H:%M:%S-06:00")

        return PostMetadata(
            title_en=datos.get("title_en", topic),
            title_es=datos.get("title_es", topic),
            description_en=datos.get("description_en", ""),
            description_es=datos.get("description_es", ""),
            tags=datos.get("tags", ["ai"]),
            category=datos.get("category", "ai"),
            slug=datos.get("slug", topic.lower().replace(" ", "-")[:50]),
            date=fecha_iso,
        )

    def _run_review_cycle(
        self,
        post: GeneratedPost,
        topic: str,
        context: str | None = None,
    ) -> GeneratedPost:
        """
        Ejecuta el ciclo de self-review con correcciones.

        Flujo:
        1. Revisa el post actual
        2. Si pasa → listo
        3. Si no pasa → corrige basándose en las sugerencias
        4. Repite hasta pasar o llegar al máximo de iteraciones

        ¿Por qué máximo 2 iteraciones?
        Para evitar loops infinitos. Si después de 2 correcciones
        no pasa, algo fundamental está mal y es mejor que un humano
        lo revise.

        Args:
            post: Post generado a revisar
            topic: Tema original (para regenerar si necesario)
            context: Contexto adicional

        Returns:
            GeneratedPost actualizado con estado de review.
        """
        max_iteraciones = self._config.mikalia.max_review_iterations

        for iteracion in range(max_iteraciones):
            post.review_iterations = iteracion + 1

            # Ejecutar review
            resultado = self._reviewer.review(
                en_content=post.content_en,
                es_content=post.content_es,
            )

            if resultado.approved:
                post.review_passed = True
                return post

            # Si no pasó, mostrar sugerencias y corregir
            logger.warning(
                f"Review no aprobado (iteración {iteracion + 1}). "
                f"Sugerencias: {', '.join(resultado.suggestions)}"
            )

            if iteracion < max_iteraciones - 1:
                # Corregir basándose en las sugerencias
                logger.step(
                    5, 6,
                    f"Corrigiendo post (iteración {iteracion + 2})..."
                )
                post.content_en = self._apply_corrections(
                    post.content_en, resultado.suggestions, "en"
                )
                post.content_es = self._apply_corrections(
                    post.content_es, resultado.suggestions, "es"
                )

        return post

    def _apply_corrections(
        self,
        content: str,
        suggestions: list[str],
        lang: str,
    ) -> str:
        """
        Aplica correcciones a un post basándose en sugerencias del review.

        En vez de regenerar el post completo (caro y pierde lo bueno),
        le pedimos a Claude que corrija solo los problemas específicos.

        Args:
            content: Contenido actual del post
            suggestions: Lista de sugerencias del reviewer
            lang: Idioma ("en" o "es")

        Returns:
            Contenido corregido.
        """
        idioma = "English" if lang == "en" else "Spanish"
        sugerencias = "\n".join(f"- {s}" for s in suggestions)

        prompt = f"""Improve this {idioma} blog post based on the following review feedback.

Review suggestions:
{sugerencias}

Current post:
{content}

Instructions:
- Apply ONLY the suggested corrections
- Do NOT rewrite the entire post
- Maintain the same structure and voice
- Return the complete corrected post"""

        respuesta = self._client.generate(
            user_prompt=prompt,
            temperature=0.5,  # Balance entre creatividad y precisión
            max_tokens=self._config.mikalia.max_tokens,
        )

        return respuesta.content
