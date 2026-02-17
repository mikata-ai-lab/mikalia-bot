"""
test_blog_post.py — Tests para BlogPostTool.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mikalia.tools.blog_post import BlogPostTool, _slugify


# ================================================================
# _slugify
# ================================================================

class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self):
        assert _slugify("What's New in AI?") == "whats-new-in-ai"

    def test_multiple_spaces(self):
        assert _slugify("too   many   spaces") == "too-many-spaces"

    def test_truncates_long_slugs(self):
        result = _slugify("a" * 200)
        assert len(result) <= 80

    def test_strips_dashes(self):
        assert _slugify("--hello--") == "hello"


# ================================================================
# BlogPostTool
# ================================================================

class TestBlogPostTool:
    def test_name_and_definition(self):
        tool = BlogPostTool(blog_path="/tmp/fake-blog")
        assert tool.name == "blog_post"
        d = tool.to_claude_definition()
        assert "title_en" in d["input_schema"]["properties"]
        assert "title_es" in d["input_schema"]["properties"]
        assert "content_en" in d["input_schema"]["properties"]
        assert "content_es" in d["input_schema"]["properties"]

    def test_creates_post_files(self, tmp_path):
        # Crear estructura minima de blog
        blog = tmp_path / "fake-blog"
        (blog / "content" / "blog").mkdir(parents=True)

        tool = BlogPostTool(blog_path=blog)
        result = tool.execute(
            title_en="Test Post",
            title_es="Post de Prueba",
            content_en="Hello world!",
            content_es="Hola mundo!",
            slug="test-post",
            tags="ai, testing",
            category="technical",
            git_push=False,
        )

        assert result.success
        assert "test-post" in result.output

        # Verificar archivos
        en_file = blog / "content" / "blog" / "test-post" / "index.md"
        es_file = blog / "content" / "blog" / "test-post" / "index.es.md"
        assert en_file.exists()
        assert es_file.exists()

        # Verificar contenido EN
        en_content = en_file.read_text(encoding="utf-8")
        assert 'title: "Test Post"' in en_content
        assert "Hello world!" in en_content
        assert '"ai"' in en_content
        assert '"testing"' in en_content
        assert "technical" in en_content

        # Verificar contenido ES
        es_content = es_file.read_text(encoding="utf-8")
        assert 'title: "Post de Prueba"' in es_content
        assert "Hola mundo!" in es_content

    def test_auto_generates_slug(self, tmp_path):
        blog = tmp_path / "blog"
        (blog / "content" / "blog").mkdir(parents=True)

        tool = BlogPostTool(blog_path=blog)
        result = tool.execute(
            title_en="My Amazing AI Post!",
            title_es="Mi Increible Post de IA!",
            content_en="Content here",
            content_es="Contenido aqui",
            git_push=False,
        )

        assert result.success
        assert "my-amazing-ai-post" in result.output

    def test_auto_generates_description(self, tmp_path):
        blog = tmp_path / "blog"
        (blog / "content" / "blog").mkdir(parents=True)

        tool = BlogPostTool(blog_path=blog)
        result = tool.execute(
            title_en="Auto Desc Test",
            title_es="Test Auto Desc",
            content_en="This is a long content " * 20,
            content_es="Este es contenido largo " * 20,
            slug="auto-desc",
            git_push=False,
        )

        assert result.success
        en_file = blog / "content" / "blog" / "auto-desc" / "index.md"
        content = en_file.read_text(encoding="utf-8")
        assert 'description: "This is a long' in content

    def test_fails_if_blog_not_found(self):
        tool = BlogPostTool(blog_path="/nonexistent/path")
        result = tool.execute(
            title_en="Test",
            title_es="Test",
            content_en="x",
            content_es="x",
            git_push=False,
        )
        assert not result.success
        assert "no encontrado" in result.error.lower()

    def test_frontmatter_has_correct_format(self, tmp_path):
        blog = tmp_path / "blog"
        (blog / "content" / "blog").mkdir(parents=True)

        tool = BlogPostTool(blog_path=blog)
        tool.execute(
            title_en="Format Check",
            title_es="Verificar Formato",
            content_en="body",
            content_es="cuerpo",
            slug="format-check",
            git_push=False,
        )

        en_file = blog / "content" / "blog" / "format-check" / "index.md"
        content = en_file.read_text(encoding="utf-8")

        # Verificar frontmatter Hugo
        assert content.startswith("---\n")
        assert "draft: false" in content
        assert "showHero: true" in content
        assert 'heroStyle: "big"' in content
        assert 'series: ["Building Mikalia"]' in content

    def test_url_in_output(self, tmp_path):
        blog = tmp_path / "blog"
        (blog / "content" / "blog").mkdir(parents=True)

        tool = BlogPostTool(blog_path=blog)
        result = tool.execute(
            title_en="URL Test",
            title_es="Test URL",
            content_en="x",
            content_es="x",
            slug="url-test",
            git_push=False,
        )

        assert "mikata-ai-lab.github.io/blog/url-test/" in result.output
