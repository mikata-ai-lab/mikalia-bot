"""
test_self_review.py — Tests para el módulo de self-review.

Verificamos que:
1. Las respuestas APPROVED se parsean correctamente
2. Las respuestas NEEDS_REVISION extraen las sugerencias
3. Los formatos inesperados se manejan con fail-safe
"""

import pytest

from mikalia.generation.self_review import SelfReviewer, ReviewResult


class TestParseReview:
    """Tests para el parseo de respuestas de review."""

    @pytest.fixture
    def reviewer(self):
        """Crea un SelfReviewer con mocks (no necesita API real)."""
        # Creamos una instancia sin cliente real para testear _parse_review
        reviewer = object.__new__(SelfReviewer)
        return reviewer

    def test_aprobado_simple(self, reviewer):
        """Respuesta 'APPROVED' debe dar approved=True."""
        resultado = reviewer._parse_review("APPROVED")
        assert resultado.approved is True
        assert resultado.suggestions == []

    def test_aprobado_con_texto_extra(self, reviewer):
        """'APPROVED' con texto adicional sigue siendo aprobado."""
        resultado = reviewer._parse_review("APPROVED\nGreat post!")
        assert resultado.approved is True

    def test_necesita_revision(self, reviewer):
        """NEEDS_REVISION debe extraer sugerencias."""
        respuesta = """NEEDS_REVISION
- The introduction could be more engaging
- Spanish version sounds too literal in paragraph 3
- Missing code example for the main concept"""
        resultado = reviewer._parse_review(respuesta)
        assert resultado.approved is False
        assert len(resultado.suggestions) == 3
        assert "introduction" in resultado.suggestions[0].lower()

    def test_formato_inesperado(self, reviewer):
        """Formato no reconocido debe tratarse como no aprobado (fail-safe)."""
        resultado = reviewer._parse_review("The post is okay I guess")
        assert resultado.approved is False
        assert len(resultado.suggestions) > 0

    def test_respuesta_vacia(self, reviewer):
        """Respuesta vacía debe ser no aprobada."""
        resultado = reviewer._parse_review("")
        assert resultado.approved is False

    def test_raw_response_guardada(self, reviewer):
        """La respuesta cruda debe guardarse para debugging."""
        texto = "APPROVED"
        resultado = reviewer._parse_review(texto)
        assert resultado.raw_response == texto
