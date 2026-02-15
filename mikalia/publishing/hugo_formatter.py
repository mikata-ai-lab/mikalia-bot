"""
hugo_formatter.py — Traduce contenido de Mikalia a formato Hugo.

Hugo usa archivos Markdown con "front matter" YAML al inicio.
El blog de Mikata AI Lab usa el tema Blowfish con page bundles:

    content/blog/{slug}/
    ├── index.md      ← Post en inglés
    └── index.es.md   ← Post en español

Cada archivo tiene front matter (metadata) + contenido markdown.

¿Qué es front matter?
    Es un bloque YAML al inicio del archivo entre --- que Hugo
    usa para metadata: título, fecha, tags, etc.

    ---
    title: "Mi Título"
    date: 2026-02-15T12:00:00-06:00
    draft: false
    ...
    ---

    Aquí va el contenido en markdown...

¿Qué son page bundles?
    En vez de un archivo suelto, cada post es un DIRECTORIO con
    sus archivos dentro. Esto permite que cada post tenga sus
    propias imágenes, datos, etc. Blowfish requiere este formato.

Nota sobre timezone:
    Usamos -06:00 (CST = Central Standard Time, Monterrey, México)

Uso:
    from mikalia.publishing.hugo_formatter import HugoFormatter
    formatter = HugoFormatter(config)
    archivos = formatter.format_post(post)
    # archivos = {Path("content/blog/mi-slug/index.md"): "contenido...", ...}
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from mikalia.config import AppConfig
from mikalia.generation.post_generator import GeneratedPost
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.publishing")


@dataclass
class FormattedFiles:
    """
    Archivos formateados listos para escribir al disco.

    Attributes:
        files: Dict de {ruta_relativa: contenido} para cada archivo
        slug: Slug del post (nombre del directorio)
        directory: Ruta del directorio del post (relativa al repo)
    """
    files: dict[Path, str]
    slug: str
    directory: Path


class HugoFormatter:
    """
    Formatea posts generados en archivos compatibles con Hugo/Blowfish.

    Se encarga de:
    - Generar front matter YAML válido
    - Crear rutas correctas (page bundles de Blowfish)
    - Sanitizar slugs para URLs amigables
    - Validar que la estructura sea correcta

    Args:
        config: Configuración de la app (para rutas y autor)
    """

    def __init__(self, config: AppConfig):
        self._config = config

    def format_post(self, post: GeneratedPost) -> FormattedFiles:
        """
        Formatea un post generado en archivos Hugo listos para escribir.

        Genera dos archivos:
        1. index.md — Post en inglés con front matter
        2. index.es.md — Post en español con front matter

        Ambos van en el directorio: content/blog/{slug}/

        Args:
            post: Post generado con contenido bilingüe y metadata.

        Returns:
            FormattedFiles con los archivos y sus rutas.
        """
        slug = self._sanitize_slug(post.metadata.slug)
        directorio = Path(self._config.blog.content_base) / slug

        # Generar archivo en inglés
        en_content = self._build_file(
            title=post.metadata.title_en,
            description=post.metadata.description_en,
            date=post.metadata.date,
            tags=post.metadata.tags,
            category=post.metadata.category,
            content=post.content_en,
        )

        # Generar archivo en español
        es_content = self._build_file(
            title=post.metadata.title_es,
            description=post.metadata.description_es,
            date=post.metadata.date,
            tags=post.metadata.tags,
            category=post.metadata.category,
            content=post.content_es,
        )

        # Construir rutas usando nombres de archivo de la config
        archivos = {
            directorio / self._config.blog.en_filename: en_content,
            directorio / self._config.blog.es_filename: es_content,
        }

        logger.info(f"Post formateado en: {directorio}/")
        return FormattedFiles(
            files=archivos,
            slug=slug,
            directory=directorio,
        )

    def _build_file(
        self,
        title: str,
        description: str,
        date: str,
        tags: list[str],
        category: str,
        content: str,
    ) -> str:
        """
        Construye un archivo markdown con front matter Hugo.

        El front matter se genera manualmente (no con yaml.dump)
        para tener control total sobre el formato y evitar
        caracteres escapados innecesarios.

        Args:
            title: Título del post
            description: Descripción SEO
            date: Fecha ISO 8601
            tags: Lista de tags
            category: Categoría
            content: Contenido markdown

        Returns:
            String con front matter + contenido listo para escribir.
        """
        # Escapar comillas en título y descripción
        title_safe = title.replace('"', '\\"')
        desc_safe = description.replace('"', '\\"')

        # Construir tags YAML
        tags_yaml = "\n".join(f'  - "{tag}"' for tag in tags)

        # Construir front matter
        front_matter = f"""---
title: "{title_safe}"
date: {date}
draft: false
description: "{desc_safe}"
tags:
{tags_yaml}
categories:
  - "{category}"
series: ["Building Mikalia"]
showHero: true
heroStyle: "big"
---"""

        # Combinar front matter + contenido
        # Asegurarnos de que hay exactamente un newline entre front matter y contenido
        return f"{front_matter}\n\n{content.strip()}\n"

    def _sanitize_slug(self, slug: str) -> str:
        """
        Sanitiza un slug para que sea válido como URL y nombre de directorio.

        Reglas:
        - Solo letras minúsculas, números y guiones
        - Sin caracteres especiales ni acentos
        - Sin guiones dobles o al inicio/final
        - Máximo 50 caracteres

        ¿Por qué sanitizar?
        Porque el slug se usa tanto en la URL como en el filesystem.
        Caracteres especiales pueden causar problemas en ambos contextos.

        Args:
            slug: Slug crudo (puede tener chars especiales).

        Returns:
            Slug sanitizado y seguro.

        Ejemplos:
            "Building AI Agents" → "building-ai-agents"
            "¿Cómo usar Claude?" → "como-usar-claude"
            "Post #1: My First!!!" → "post-1-my-first"
        """
        # Paso 1: Normalizar unicode (quitar acentos)
        # NFD descompone caracteres: á → a + ́
        # Luego filtramos las marcas de combinación (acentos)
        slug = unicodedata.normalize("NFD", slug)
        slug = "".join(c for c in slug if unicodedata.category(c) != "Mn")

        # Paso 2: Minúsculas
        slug = slug.lower()

        # Paso 3: Reemplazar espacios y caracteres no alfanuméricos con guiones
        slug = re.sub(r"[^a-z0-9]+", "-", slug)

        # Paso 4: Eliminar guiones al inicio/final y guiones dobles
        slug = re.sub(r"-+", "-", slug).strip("-")

        # Paso 5: Truncar a 50 caracteres (sin cortar en medio de palabra)
        if len(slug) > 50:
            slug = slug[:50].rsplit("-", 1)[0]

        return slug
