"""
test_rag_pipeline.py — Tests para RagPipelineTool.

Verifica:
- Indexacion de texto y archivos
- Busqueda con y sin resultados
- Status del indice
- Error sin VectorMemory
- Metodo _chunk_text
- Metadata del tool
"""

from __future__ import annotations

import pytest
from pathlib import Path

from mikalia.tools.rag_pipeline import RagPipelineTool
from mikalia.tools.base import ToolResult


class MockVectorMemory:
    """Vector memory mock que almacena documentos en memoria."""

    def __init__(self):
        self._documents: list[str] = []
        self._metadata: list[dict | None] = []

    def add(self, text: str, metadata: dict | None = None) -> None:
        self._documents.append(text)
        self._metadata.append(metadata)

    def search(self, query: str, top_k: int = 3) -> list[tuple[str, float, dict | None]]:
        if self._documents:
            # Retorna el primer documento con score alto
            return [(self._documents[0], 0.9, self._metadata[0])]
        return []


# ================================================================
# Indexacion
# ================================================================

class TestRagIndexing:
    def test_index_text(self):
        """Indexar texto directamente."""
        vm = MockVectorMemory()
        tool = RagPipelineTool(vector_memory=vm)

        result = tool.execute(
            action="index",
            text="Python es un lenguaje de programacion versatil.",
            source_name="python_docs",
        )
        assert result.success
        assert "python_docs" in result.output
        assert "Chunks creados" in result.output
        assert len(vm._documents) >= 1

    def test_index_file(self, tmp_path):
        """Indexar un archivo desde disco."""
        vm = MockVectorMemory()
        tool = RagPipelineTool(vector_memory=vm)

        # Crear archivo temporal con contenido
        doc_file = tmp_path / "manual.txt"
        doc_file.write_text(
            "Capitulo 1: Introduccion\n\n"
            "Este es un manual de usuario para la aplicacion.\n\n"
            "Capitulo 2: Instalacion\n\n"
            "Descarga el paquete desde el sitio oficial.",
            encoding="utf-8",
        )

        result = tool.execute(
            action="index",
            file_path=str(doc_file),
        )
        assert result.success
        assert "manual.txt" in result.output
        assert "Chunks creados" in result.output
        assert len(vm._documents) >= 1


# ================================================================
# Query
# ================================================================

class TestRagQuery:
    def test_query_with_results(self):
        """Query retorna chunks relevantes."""
        vm = MockVectorMemory()
        tool = RagPipelineTool(vector_memory=vm)

        # Indexar algo primero
        tool.execute(
            action="index",
            text="Mikalia es un agente de AI creado por Mikata.",
            source_name="about",
        )

        result = tool.execute(
            action="query",
            text="Quien creo Mikalia?",
        )
        assert result.success
        assert "Fuentes:" in result.output

    def test_query_no_results(self):
        """Query sin documentos indexados indica que no hay resultados."""
        vm = MockVectorMemory()
        tool = RagPipelineTool(vector_memory=vm)

        result = tool.execute(
            action="query",
            text="Donde esta la documentacion?",
        )
        assert result.success
        assert "No se encontraron" in result.output


# ================================================================
# Status
# ================================================================

class TestRagStatus:
    def test_status(self):
        """Status muestra estadisticas del indice."""
        vm = MockVectorMemory()
        tool = RagPipelineTool(vector_memory=vm)

        # Indexar datos
        tool.execute(action="index", text="Documento uno.", source_name="doc1")
        tool.execute(action="index", text="Documento dos.", source_name="doc2")

        result = tool.execute(action="status")
        assert result.success
        assert "RAG Pipeline Status" in result.output
        assert "Total chunks indexados" in result.output


# ================================================================
# Edge cases y utilidades
# ================================================================

class TestRagEdgeCases:
    def test_no_vector_memory_error(self):
        """Sin VectorMemory retorna error."""
        tool = RagPipelineTool(vector_memory=None)
        result = tool.execute(action="index", text="algo")
        assert not result.success
        assert "VectorMemory" in result.error

    def test_chunk_text_method(self):
        """_chunk_text divide texto correctamente."""
        tool = RagPipelineTool()

        # Texto con multiples parrafos
        text = (
            "Primer parrafo con informacion importante.\n\n"
            "Segundo parrafo con mas detalles.\n\n"
            "Tercer parrafo con conclusiones."
        )
        chunks = tool._chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) >= 1
        # Todos los parrafos deberian estar representados
        combined = " ".join(chunks)
        assert "Primer" in combined
        assert "Segundo" in combined
        assert "Tercer" in combined

    def test_chunk_text_splits_long_paragraphs(self):
        """Parrafos mas largos que chunk_size se subdividen."""
        tool = RagPipelineTool()

        # Crear un parrafo largo
        long_text = "Esta es una oracion larga. " * 100
        chunks = tool._chunk_text(long_text, chunk_size=200, overlap=20)
        assert len(chunks) > 1
        for chunk in chunks:
            # Cada chunk no deberia exceder significativamente el chunk_size
            assert len(chunk) < 500

    def test_tool_metadata(self):
        """Metadata del tool es correcta."""
        tool = RagPipelineTool()
        assert tool.name == "rag_pipeline"
        assert "RAG" in tool.description

        defn = tool.to_claude_definition()
        assert defn["name"] == "rag_pipeline"
        assert "input_schema" in defn
        assert "action" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["properties"]["action"]["enum"] == [
            "index", "query", "status"
        ]
