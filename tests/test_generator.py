"""
test_generator.py — Tests para el generador de posts.

Estos tests usan mocks para no hacer llamadas reales a la API.
Verificamos que:
1. El flujo de generación es correcto
2. La metadata se parsea correctamente
3. Los reintentos de review funcionan
"""

from unittest.mock import MagicMock, patch
import json

import pytest

from mikalia.config import AppConfig
from mikalia.generation.client import MikaliaClient, APIResponse
from mikalia.generation.post_generator import PostGenerator, PostMetadata


@pytest.fixture
def mock_client():
    """Crea un MikaliaClient mockeado que no hace llamadas reales."""
    client = MagicMock(spec=MikaliaClient)
    return client


@pytest.fixture
def generator(mock_client):
    """Crea un PostGenerator con cliente mockeado."""
    config = AppConfig()
    gen = PostGenerator(mock_client, config)
    return gen


class TestGenerateMetadata:
    """Tests para la generación de metadata."""

    def test_parsea_json_valido(self, generator, mock_client):
        """Debe parsear correctamente una respuesta JSON."""
        metadata_json = json.dumps({
            "title_en": "Test Title",
            "title_es": "Título de Prueba",
            "description_en": "A test description",
            "description_es": "Una descripción de prueba",
            "tags": ["test", "ai"],
            "category": "tutorials",
            "slug": "test-title",
        })

        mock_client.generate.return_value = APIResponse(
            content=metadata_json,
            model="test",
            input_tokens=100,
            output_tokens=50,
            stop_reason="end_turn",
        )

        resultado = generator._generate_metadata(
            content_en="test content",
            topic="Test Topic",
        )

        assert isinstance(resultado, PostMetadata)
        assert resultado.title_en == "Test Title"
        assert resultado.title_es == "Título de Prueba"
        assert resultado.slug == "test-title"
        assert len(resultado.tags) == 2

    def test_category_override(self, generator, mock_client):
        """Si se da una categoría, debe sobrescribir la generada."""
        metadata_json = json.dumps({
            "title_en": "T", "title_es": "T",
            "description_en": "D", "description_es": "D",
            "tags": ["t"], "category": "ai", "slug": "s",
        })
        mock_client.generate.return_value = APIResponse(
            content=metadata_json, model="test",
            input_tokens=0, output_tokens=0, stop_reason="end_turn",
        )

        resultado = generator._generate_metadata(
            content_en="test",
            topic="test",
            category="tutorials",
        )

        assert resultado.category == "tutorials"

    def test_json_invalido_usa_defaults(self, generator, mock_client):
        """Si el JSON es inválido, debe usar valores por defecto."""
        mock_client.generate.return_value = APIResponse(
            content="not valid json at all",
            model="test",
            input_tokens=0, output_tokens=0, stop_reason="end_turn",
        )

        resultado = generator._generate_metadata(
            content_en="test",
            topic="My Test Topic",
        )

        # Debe funcionar sin crashear
        assert isinstance(resultado, PostMetadata)
        assert resultado.date  # Debe tener fecha
