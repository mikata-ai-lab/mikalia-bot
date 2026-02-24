"""
rag_pipeline.py — RAG (Retrieval-Augmented Generation) para Mikalia.

Pipeline completo: chunk → embed → store → retrieve → generate.
Usa el VectorMemory existente como backend.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.rag_pipeline")

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
MAX_CHUNKS = 200


class RagPipelineTool(BaseTool):
    """Pipeline RAG: indexa documentos y responde con contexto."""

    def __init__(self, client=None, vector_memory=None) -> None:
        self._client = client
        self._vector = vector_memory

    @property
    def name(self) -> str:
        return "rag_pipeline"

    @property
    def description(self) -> str:
        return (
            "RAG (Retrieval-Augmented Generation) pipeline. Actions: "
            "index (chunk and store a document), "
            "query (search indexed docs and answer with context), "
            "status (show indexed documents). "
            "Use to answer questions about specific documents or knowledge bases."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: index, query, or status",
                    "enum": ["index", "query", "status"],
                },
                "text": {
                    "type": "string",
                    "description": "Document text to index (for 'index') or question (for 'query')",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to file to index (alternative to text)",
                },
                "source_name": {
                    "type": "string",
                    "description": "Name/label for the document being indexed",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of chunks to retrieve (default: 3)",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        text: str = "",
        file_path: str = "",
        source_name: str = "",
        top_k: int = 3,
        **_: Any,
    ) -> ToolResult:
        if not self._vector:
            return ToolResult(
                success=False,
                error="RAG pipeline necesita VectorMemory para funcionar",
            )

        if action == "index":
            return self._index(text, file_path, source_name)
        elif action == "query":
            return self._query(text, top_k)
        elif action == "status":
            return self._status()
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _index(self, text: str, file_path: str, source_name: str) -> ToolResult:
        """Indexa un documento: chunk → store."""
        content = ""

        if file_path:
            path = Path(file_path)
            if not path.exists():
                return ToolResult(success=False, error=f"Archivo no encontrado: {file_path}")
            content = path.read_text(encoding="utf-8")
            source_name = source_name or path.name
        elif text:
            content = text
            source_name = source_name or f"doc_{hashlib.md5(text[:100].encode()).hexdigest()[:8]}"
        else:
            return ToolResult(success=False, error="Proporciona text o file_path")

        # Chunk the document
        chunks = self._chunk_text(content, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP)

        if len(chunks) > MAX_CHUNKS:
            chunks = chunks[:MAX_CHUNKS]

        # Store each chunk
        stored = 0
        for i, chunk in enumerate(chunks):
            chunk_id = f"rag:{source_name}:chunk_{i}"
            self._vector.add(chunk, metadata={"source": source_name, "chunk_id": chunk_id})
            stored += 1

        logger.success(f"RAG: indexado '{source_name}' ({stored} chunks)")
        return ToolResult(
            success=True,
            output=(
                f"Documento indexado: {source_name}\n"
                f"Chunks creados: {stored}\n"
                f"Tamano original: {len(content)} chars"
            ),
        )

    def _query(self, question: str, top_k: int) -> ToolResult:
        """Busca chunks relevantes y genera respuesta."""
        if not question:
            return ToolResult(success=False, error="Pregunta requerida")

        top_k = min(max(top_k, 1), 10)

        # Retrieve relevant chunks
        results = self._vector.search(question, top_k=top_k)

        if not results:
            return ToolResult(
                success=True,
                output="No se encontraron documentos relevantes. Indexa documentos primero.",
            )

        # Build context from retrieved chunks
        context_parts = []
        sources = set()
        for text, score, metadata in results:
            context_parts.append(text)
            if metadata and "source" in metadata:
                sources.add(metadata["source"])

        context = "\n---\n".join(context_parts)

        # Generate answer with context
        if self._client:
            answer = self._generate_answer(question, context)
        else:
            answer = f"Contexto encontrado ({len(results)} chunks):\n{context[:2000]}"

        source_list = ", ".join(sources) if sources else "desconocida"
        return ToolResult(
            success=True,
            output=f"{answer}\n\nFuentes: {source_list}",
        )

    def _status(self) -> ToolResult:
        """Muestra estadisticas del indice."""
        total = len(self._vector._documents) if hasattr(self._vector, "_documents") else 0

        # Contar por fuente
        sources: dict[str, int] = {}
        if hasattr(self._vector, "_metadata"):
            for meta in self._vector._metadata:
                if meta and "source" in meta:
                    src = meta["source"]
                    sources[src] = sources.get(src, 0) + 1

        lines = [
            "=== RAG Pipeline Status ===",
            f"Total chunks indexados: {total}",
        ]

        if sources:
            lines.append("\nDocumentos:")
            for src, count in sorted(sources.items()):
                lines.append(f"  {src}: {count} chunks")

        return ToolResult(success=True, output="\n".join(lines))

    def _chunk_text(
        self, text: str, chunk_size: int, overlap: int
    ) -> list[str]:
        """Divide texto en chunks con overlap."""
        # Split by paragraphs first
        paragraphs = re.split(r"\n\s*\n", text)
        chunks = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current) + len(para) < chunk_size:
                current += "\n\n" + para if current else para
            else:
                if current:
                    chunks.append(current.strip())
                # If paragraph itself is too long, split by sentences
                if len(para) > chunk_size:
                    sentences = re.split(r"[.!?]+\s+", para)
                    current = ""
                    for sent in sentences:
                        if len(current) + len(sent) < chunk_size:
                            current += ". " + sent if current else sent
                        else:
                            if current:
                                chunks.append(current.strip())
                            current = sent
                else:
                    current = para

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _generate_answer(self, question: str, context: str) -> str:
        """Genera respuesta usando Claude con contexto RAG."""
        prompt = (
            "Responde la siguiente pregunta usando SOLO la informacion "
            "del contexto proporcionado. Si la respuesta no esta en el "
            "contexto, dilo.\n\n"
            f"Contexto:\n{context}\n\n"
            f"Pregunta: {question}"
        )

        try:
            return self._client.generate(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )
        except Exception as e:
            return f"Error generando respuesta: {e}\n\nContexto encontrado:\n{context[:1000]}"
