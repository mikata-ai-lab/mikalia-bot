"""
test_hugo_formatter.py — Tests para el formateador de Hugo.

Verificamos que:
1. Los slugs se sanitizan correctamente
2. El front matter se genera con formato válido
3. Las rutas de page bundles son correctas
4. Los caracteres especiales se escapan
"""

import pytest

from mikalia.config import AppConfig
from mikalia.publishing.hugo_formatter import HugoFormatter
from mikalia.generation.post_generator import GeneratedPost, PostMetadata


@pytest.fixture
def formatter():
    """Crea un HugoFormatter con configuración por defecto."""
    config = AppConfig()
    return HugoFormatter(config)


@pytest.fixture
def sample_post():
    """Crea un post de ejemplo para testing."""
    return GeneratedPost(
        content_en="## Hello\n\nThis is a test post.\n\n*— Mikalia 🌸*",
        content_es="## Hola\n\nEste es un post de prueba.\n\n*— Mikalia 🌸*",
        metadata=PostMetadata(
            title_en="Test Post Title",
            title_es="Título del Post de Prueba",
            description_en="A test post for unit testing",
            description_es="Un post de prueba para testing",
            tags=["test", "python"],
            category="tutorials",
            slug="test-post-title",
            date="2026-02-15T12:00:00-06:00",
        ),
        review_passed=True,
        review_iterations=1,
    )


class TestSanitizeSlug:
    """Tests para la sanitización de slugs."""

    def test_slug_simple(self, formatter):
        """Convierte texto simple a slug."""
        assert formatter._sanitize_slug("Hello World") == "hello-world"

    def test_slug_con_acentos(self, formatter):
        """Elimina acentos y diacríticos."""
        assert formatter._sanitize_slug("Cómo usar IA") == "como-usar-ia"

    def test_slug_con_caracteres_especiales(self, formatter):
        """Elimina caracteres especiales."""
        assert formatter._sanitize_slug("Post #1: My First!!!") == "post-1-my-first"

    def test_slug_largo_se_trunca(self, formatter):
        """Slugs mayores a 50 chars se truncan."""
        slug_largo = "this is a very long title that should be truncated to fifty chars maximum"
        resultado = formatter._sanitize_slug(slug_largo)
        assert len(resultado) <= 50

    def test_slug_sin_guiones_dobles(self, formatter):
        """No debe haber guiones dobles."""
        resultado = formatter._sanitize_slug("hello---world")
        assert "--" not in resultado

    def test_slug_sin_guiones_al_inicio_final(self, formatter):
        """No debe empezar ni terminar con guión."""
        resultado = formatter._sanitize_slug("--hello-world--")
        assert not resultado.startswith("-")
        assert not resultado.endswith("-")


class TestFormatPost:
    """Tests para el formateo completo de posts."""

    def test_genera_dos_archivos(self, formatter, sample_post):
        """Debe generar exactamente 2 archivos (EN y ES)."""
        resultado = formatter.format_post(sample_post)
        assert len(resultado.files) == 2

    def test_rutas_page_bundle(self, formatter, sample_post):
        """Las rutas deben seguir el formato de page bundles de Blowfish."""
        resultado = formatter.format_post(sample_post)
        rutas = list(resultado.files.keys())
        rutas_str = [str(r) for r in rutas]

        # Debe haber index.md e index.es.md
        assert any("index.md" in str(r) and "index.es" not in str(r) for r in rutas)
        assert any("index.es.md" in str(r) for r in rutas)

    def test_front_matter_presente(self, formatter, sample_post):
        """Los archivos deben tener front matter YAML."""
        resultado = formatter.format_post(sample_post)
        for contenido in resultado.files.values():
            assert contenido.startswith("---")
            assert contenido.count("---") >= 2

    def test_titulo_en_front_matter(self, formatter, sample_post):
        """El título debe estar en el front matter."""
        resultado = formatter.format_post(sample_post)
        for ruta, contenido in resultado.files.items():
            if "index.es" in str(ruta):
                assert "Título del Post de Prueba" in contenido
            else:
                assert "Test Post Title" in contenido

    def test_tags_en_front_matter(self, formatter, sample_post):
        """Los tags deben estar en el front matter."""
        resultado = formatter.format_post(sample_post)
        for contenido in resultado.files.values():
            assert '"test"' in contenido
            assert '"python"' in contenido
