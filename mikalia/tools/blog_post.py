"""
blog_post.py — Tool para que Mikalia publique posts en el blog de Hugo.

Crea posts bilingues (EN/ES) con frontmatter correcto para Hugo + Blowfish.
Escribe directamente al repositorio del blog y opcionalmente hace git commit + push.

Uso:
    from mikalia.tools.blog_post import BlogPostTool
    tool = BlogPostTool()
    result = tool.execute(
        slug="my-post",
        title_en="My Post",
        title_es="Mi Post",
        content_en="...",
        content_es="...",
    )
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.blog_post")

# Ruta relativa al blog desde mikalia-bot
DEFAULT_BLOG_PATH = Path(__file__).parent.parent.parent.parent / "mikata-ai"

FRONTMATTER_TEMPLATE = """---
title: "{title}"
date: {date}
draft: false
description: "{description}"
tags: [{tags}]
categories: ["{category}"]
series: ["Building Mikalia"]
showHero: true
heroStyle: "big"
---

"""


def _slugify(text: str) -> str:
    """Convierte texto a slug URL-safe."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:80]


class BlogPostTool(BaseTool):
    """Crea y publica posts bilingues en el blog de Hugo."""

    def __init__(self, blog_path: str | Path | None = None) -> None:
        self._blog_path = Path(blog_path) if blog_path else DEFAULT_BLOG_PATH

    @property
    def name(self) -> str:
        return "blog_post"

    @property
    def description(self) -> str:
        return (
            "Create and publish a bilingual blog post (EN/ES) to the Hugo blog. "
            "Creates proper Hugo+Blowfish frontmatter, writes index.md and index.es.md, "
            "and optionally commits and pushes to GitHub. "
            "Provide both English and Spanish content. "
            "The post will be live after GitHub Actions deploys."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "URL slug for the post (e.g. 'my-cool-post'). Auto-generated from title_en if not provided.",
                },
                "title_en": {
                    "type": "string",
                    "description": "Post title in English",
                },
                "title_es": {
                    "type": "string",
                    "description": "Post title in Spanish",
                },
                "description_en": {
                    "type": "string",
                    "description": "Short description in English (1-2 sentences)",
                },
                "description_es": {
                    "type": "string",
                    "description": "Short description in Spanish (1-2 sentences)",
                },
                "content_en": {
                    "type": "string",
                    "description": "Full post content in English (markdown)",
                },
                "content_es": {
                    "type": "string",
                    "description": "Full post content in Spanish (markdown)",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags (e.g. 'ai-agents, python, tutorial')",
                },
                "category": {
                    "type": "string",
                    "description": "Category: ai, dev-journal, tutorials, technical, opinion, stories",
                    "default": "ai",
                },
                "git_push": {
                    "type": "boolean",
                    "description": "Whether to git commit and push (default true)",
                    "default": True,
                },
            },
            "required": ["title_en", "title_es", "content_en", "content_es"],
        }

    def execute(
        self,
        title_en: str,
        title_es: str,
        content_en: str,
        content_es: str,
        slug: str = "",
        description_en: str = "",
        description_es: str = "",
        tags: str = "ai-agents",
        category: str = "ai",
        git_push: bool = True,
        **_: Any,
    ) -> ToolResult:
        # Validar que el blog existe
        if not self._blog_path.exists():
            return ToolResult(
                success=False,
                error=(
                    f"Blog no encontrado en: {self._blog_path}. "
                    f"Verifica que el repo mikata-ai esta en la ruta correcta."
                ),
            )

        # Generar slug si no se proporciono
        if not slug:
            slug = _slugify(title_en)

        # Preparar directorio del post
        content_dir = self._blog_path / "content" / "blog" / slug
        content_dir.mkdir(parents=True, exist_ok=True)

        # Formatear tags
        tag_list = [t.strip().strip('"').strip("'") for t in tags.split(",")]
        tags_formatted = ", ".join(f'"{t}"' for t in tag_list)

        # Fecha actual en formato Hugo
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%dT%H:%M:%S-06:00")

        # Auto-generar descripcion si no se proporciono
        if not description_en:
            description_en = content_en[:150].replace('"', "'").replace("\n", " ").strip()
            if len(content_en) > 150:
                description_en += "..."
        if not description_es:
            description_es = content_es[:150].replace('"', "'").replace("\n", " ").strip()
            if len(content_es) > 150:
                description_es += "..."

        # Crear archivo EN
        en_frontmatter = FRONTMATTER_TEMPLATE.format(
            title=title_en.replace('"', '\\"'),
            date=date_str,
            description=description_en.replace('"', '\\"'),
            tags=tags_formatted,
            category=category,
        )
        en_file = content_dir / "index.md"
        en_file.write_text(en_frontmatter + content_en, encoding="utf-8")

        # Crear archivo ES
        es_frontmatter = FRONTMATTER_TEMPLATE.format(
            title=title_es.replace('"', '\\"'),
            date=date_str,
            description=description_es.replace('"', '\\"'),
            tags=tags_formatted,
            category=category,
        )
        es_file = content_dir / "index.es.md"
        es_file.write_text(es_frontmatter + content_es, encoding="utf-8")

        logger.success(f"Post creado: {content_dir}")

        # Git commit + push si se solicita
        git_result = ""
        if git_push:
            git_result = self._git_publish(slug, title_en)

        return ToolResult(
            success=True,
            output=(
                f"Post publicado!\n"
                f"Slug: {slug}\n"
                f"EN: {en_file}\n"
                f"ES: {es_file}\n"
                f"URL: https://mikata-ai-lab.github.io/blog/{slug}/\n"
                f"{git_result}"
            ),
        )

    def _git_publish(self, slug: str, title_en: str) -> str:
        """Hace git add, commit y push del post."""
        blog = str(self._blog_path)
        post_path = f"content/blog/{slug}/"

        try:
            # git add
            subprocess.run(
                ["git", "add", post_path],
                cwd=blog, capture_output=True, text=True, timeout=15,
            )

            # git commit
            commit_msg = f"Add post: {title_en}\n\nPublished by Mikalia Core"
            result = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=blog, capture_output=True, text=True, timeout=15,
            )

            if result.returncode != 0:
                return f"Git commit: {result.stderr or result.stdout}"

            # git push
            result = subprocess.run(
                ["git", "push"],
                cwd=blog, capture_output=True, text=True, timeout=30,
            )

            if result.returncode != 0:
                return f"Git push: {result.stderr or result.stdout}"

            return "Git: committed and pushed. GitHub Actions deploying..."

        except subprocess.TimeoutExpired:
            return "Git: timeout (el push puede estar lento)"
        except Exception as e:
            return f"Git: error — {e}"
