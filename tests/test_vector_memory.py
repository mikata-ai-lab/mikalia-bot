"""
test_vector_memory.py — Tests para la memoria semantica de Mikalia.

Verifica:
- Inicializacion de tabla de embeddings
- Add/delete de vectores
- Busqueda semantica por similitud
- Sincronizacion desde facts SQL
- Fallback graceful cuando modelo no esta disponible

Nota: Los tests que requieren el modelo ONNX (~25MB download)
se marcan con @pytest.mark.slow y se pueden saltar con -m "not slow".
"""

from __future__ import annotations

import sqlite3

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


# ================================================================
# Tests que NO requieren modelo (pura DB)
# ================================================================

class TestVectorMemoryDB:
    def test_init_creates_table(self, tmp_path):
        """La tabla embeddings se crea automaticamente."""
        from mikalia.core.vector_memory import VectorMemory

        db_path = str(tmp_path / "test.db")
        vm = VectorMemory(db_path, model_dir=str(tmp_path / "models"))

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_count_empty(self, tmp_path):
        """Count retorna 0 cuando no hay embeddings."""
        from mikalia.core.vector_memory import VectorMemory

        db_path = str(tmp_path / "test.db")
        vm = VectorMemory(db_path, model_dir=str(tmp_path / "models"))
        assert vm.count() == 0

    def test_delete_nonexistent(self, tmp_path):
        """Delete de un fact inexistente no falla."""
        from mikalia.core.vector_memory import VectorMemory

        db_path = str(tmp_path / "test.db")
        vm = VectorMemory(db_path, model_dir=str(tmp_path / "models"))
        vm.delete(999)  # No deberia fallar

    def test_is_model_ready_false(self, tmp_path):
        """is_model_ready es False cuando no hay modelo descargado."""
        from mikalia.core.vector_memory import VectorMemory

        db_path = str(tmp_path / "test.db")
        vm = VectorMemory(db_path, model_dir=str(tmp_path / "models"))
        assert vm.is_model_ready is False


# ================================================================
# Tests con mock de embedding (no requieren modelo real)
# ================================================================

class TestVectorMemoryMocked:
    @pytest.fixture
    def vm(self, tmp_path):
        """VectorMemory con _embed mockeado."""
        from mikalia.core.vector_memory import VectorMemory

        db_path = str(tmp_path / "test.db")
        vm = VectorMemory(db_path, model_dir=str(tmp_path / "models"))

        # Mockear _embed para generar vectores deterministicos
        def fake_embed(text: str) -> np.ndarray:
            """Genera vector basado en hash del texto (reproducible)."""
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16) % 2**31
            np.random.seed(h)
            vec = np.random.randn(384).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            return vec

        vm._embed = fake_embed
        return vm

    def test_add_and_count(self, vm):
        """Add incrementa el count."""
        vm.add(1, "Miguel vive en Monterrey")
        vm.add(2, "Mikalia es un agente autonomo")
        assert vm.count() == 2

    def test_add_updates_existing(self, vm):
        """Add con mismo fact_id actualiza el texto."""
        vm.add(1, "texto original")
        vm.add(1, "texto actualizado")
        assert vm.count() == 1

    def test_delete_removes(self, vm):
        """Delete elimina el embedding."""
        vm.add(1, "temporal")
        assert vm.count() == 1
        vm.delete(1)
        assert vm.count() == 0

    def test_search_returns_results(self, vm):
        """Search retorna resultados ordenados por score."""
        vm.add(1, "Miguel vive en Monterrey Mexico")
        vm.add(2, "Mikalia es un agente de inteligencia artificial")
        vm.add(3, "Python es un lenguaje de programacion")

        results = vm.search("donde vive Miguel", n_results=3, min_score=0.0)
        assert len(results) > 0
        assert all("score" in r for r in results)
        assert all("text" in r for r in results)

    def test_search_respects_n_results(self, vm):
        """Search limita a n_results."""
        for i in range(10):
            vm.add(i, f"fact numero {i}")

        results = vm.search("fact", n_results=3, min_score=0.0)
        assert len(results) <= 3

    def test_search_empty_returns_empty(self, vm):
        """Search sin embeddings retorna lista vacia."""
        results = vm.search("cualquier cosa")
        assert results == []

    def test_search_scores_are_sorted(self, vm):
        """Resultados vienen ordenados por score descendente."""
        vm.add(1, "gato negro")
        vm.add(2, "perro blanco")
        vm.add(3, "pajaro azul")

        results = vm.search("animal domestico", n_results=3, min_score=0.0)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_sync_from_facts(self, vm):
        """sync_from_facts indexa una lista de facts."""
        facts = [
            {"id": 1, "category": "personal", "subject": "mikata", "fact": "Vive en Monterrey"},
            {"id": 2, "category": "project", "subject": "mikalia", "fact": "Agente autonomo"},
            {"id": 3, "category": "health", "subject": "mikata", "fact": "Tiene ataxia"},
        ]
        count = vm.sync_from_facts(facts)
        assert count == 3
        assert vm.count() == 3


# ================================================================
# Tests de integracion con SearchMemoryTool
# ================================================================

class TestSearchMemoryWithVector:
    def test_search_tool_uses_vector(self, tmp_path):
        """SearchMemoryTool usa vector memory cuando disponible."""
        from mikalia.core.memory import MemoryManager
        from mikalia.tools.memory_tools import SearchMemoryTool

        db_path = str(tmp_path / "test.db")
        memory = MemoryManager(db_path, str(SCHEMA_PATH))

        # Mock vector memory
        mock_vector = MagicMock()
        mock_vector.search.return_value = [
            {"fact_id": 1, "text": "personal mikata: Vive en Monterrey", "score": 0.92},
        ]

        tool = SearchMemoryTool(memory, vector_memory=mock_vector)
        result = tool.execute(query="donde vive")

        assert result.success
        assert "92%" in result.output
        assert "Monterrey" in result.output
        mock_vector.search.assert_called_once()

    def test_search_tool_falls_back_to_sql(self, tmp_path):
        """SearchMemoryTool usa SQL cuando vector falla."""
        from mikalia.core.memory import MemoryManager
        from mikalia.tools.memory_tools import SearchMemoryTool

        db_path = str(tmp_path / "test.db")
        memory = MemoryManager(db_path, str(SCHEMA_PATH))

        # Mock vector que falla
        mock_vector = MagicMock()
        mock_vector.search.side_effect = Exception("model not loaded")

        tool = SearchMemoryTool(memory, vector_memory=mock_vector)
        result = tool.execute(query="Monterrey")

        assert result.success
        # Seed data tiene "Vive en Monterrey"
        assert "Monterrey" in result.output

    def test_search_tool_works_without_vector(self, tmp_path):
        """SearchMemoryTool funciona sin vector memory (solo SQL)."""
        from mikalia.core.memory import MemoryManager
        from mikalia.tools.memory_tools import SearchMemoryTool

        db_path = str(tmp_path / "test.db")
        memory = MemoryManager(db_path, str(SCHEMA_PATH))

        tool = SearchMemoryTool(memory, vector_memory=None)
        result = tool.execute(query="Monterrey")

        assert result.success
        assert "Monterrey" in result.output
