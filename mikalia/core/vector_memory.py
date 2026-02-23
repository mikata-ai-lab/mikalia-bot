"""
vector_memory.py — Memoria semantica para Mikalia.

Busqueda por significado usando embeddings + cosine similarity.
Usa onnxruntime + tokenizers (ligero, sin PyTorch).

El modelo all-MiniLM-L6-v2 se descarga automaticamente en primer uso (~25MB).
Los embeddings se guardan en SQLite junto con los facts.

Uso:
    from mikalia.core.vector_memory import VectorMemory
    vmem = VectorMemory(db_path="data/mikalia.db")
    vmem.add("fact_1", "Miguel vive en Monterrey")
    results = vmem.search("donde vive Mikata", n=3)
"""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path
from typing import Any

import numpy as np

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.core.vector_memory")

# Modelo ONNX de embeddings (se descarga en primer uso)
MODEL_NAME = "all-MiniLM-L6-v2"
MODEL_URL = (
    "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/"
    "resolve/main/onnx/model.onnx"
)
TOKENIZER_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # Dimensiones del modelo MiniLM


class VectorMemory:
    """
    Memoria semantica basada en embeddings.

    Almacena vectores en SQLite y busca por similitud coseno.
    Modelo: all-MiniLM-L6-v2 (ONNX, ~25MB).

    Args:
        db_path: Ruta a la base de datos SQLite.
        model_dir: Directorio para cachear el modelo ONNX.
    """

    def __init__(
        self,
        db_path: str,
        model_dir: str | None = None,
    ) -> None:
        self._db_path = db_path
        self._model_dir = Path(model_dir or self._default_model_dir())
        self._session = None  # ONNX session (lazy)
        self._tokenizer = None  # Tokenizer (lazy)
        self._init_table()

    def _default_model_dir(self) -> Path:
        """Directorio por defecto para cachear modelos."""
        return Path.home() / ".mikalia" / "models"

    def _init_table(self) -> None:
        """Crea la tabla de embeddings si no existe."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    fact_id     INTEGER PRIMARY KEY,
                    text        TEXT NOT NULL,
                    vector      BLOB NOT NULL,
                    created_at  DATETIME DEFAULT (datetime('now', 'localtime'))
                )
            """)
            conn.commit()
        finally:
            conn.close()

    # ================================================================
    # Model loading (lazy)
    # ================================================================

    def _ensure_model(self) -> None:
        """Descarga y carga el modelo ONNX si no esta listo."""
        if self._session is not None:
            return

        model_path = self._model_dir / "all-MiniLM-L6-v2.onnx"

        if not model_path.exists():
            logger.info(f"Descargando modelo {MODEL_NAME}...")
            self._download_model(model_path)

        import onnxruntime as ort
        self._session = ort.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )

        from tokenizers import Tokenizer
        tokenizer_path = self._model_dir / "tokenizer.json"
        if not tokenizer_path.exists():
            self._download_tokenizer(tokenizer_path)
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=128)
        self._tokenizer.enable_padding(length=128)

        logger.success(f"Modelo {MODEL_NAME} cargado.")

    def _download_model(self, target: Path) -> None:
        """Descarga el modelo ONNX desde HuggingFace."""
        import urllib.request
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, str(target))
        logger.success(f"Modelo descargado: {target}")

    def _download_tokenizer(self, target: Path) -> None:
        """Descarga el tokenizer desde HuggingFace."""
        import urllib.request
        url = (
            f"https://huggingface.co/{TOKENIZER_NAME}/"
            "resolve/main/tokenizer.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, str(target))
        logger.success(f"Tokenizer descargado: {target}")

    # ================================================================
    # Embedding
    # ================================================================

    def _embed(self, text: str) -> np.ndarray:
        """Genera embedding para un texto."""
        self._ensure_model()

        encoded = self._tokenizer.encode(text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
        token_type_ids = np.zeros_like(input_ids)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )

        # Mean pooling sobre los tokens (output[0] = last hidden state)
        token_embeddings = outputs[0]  # (1, seq_len, hidden_dim)
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        summed = np.sum(token_embeddings * mask_expanded, axis=1)
        counts = np.sum(mask_expanded, axis=1)
        mean_pooled = summed / np.maximum(counts, 1e-9)

        # Normalizar
        norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
        normalized = mean_pooled / np.maximum(norm, 1e-9)

        return normalized[0]  # (384,)

    # ================================================================
    # CRUD
    # ================================================================

    def add(self, fact_id: int, text: str) -> None:
        """Agrega o actualiza un fact en la memoria vectorial."""
        vector = self._embed(text)
        blob = vector.astype(np.float32).tobytes()

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings (fact_id, text, vector) "
                "VALUES (?, ?, ?)",
                (fact_id, text, blob),
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, fact_id: int) -> None:
        """Elimina un fact de la memoria vectorial."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "DELETE FROM embeddings WHERE fact_id = ?",
                (fact_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def search(
        self,
        query: str,
        n_results: int = 5,
        min_score: float = 0.3,
    ) -> list[dict]:
        """
        Busca facts similares al query por significado.

        Args:
            query: Texto de busqueda.
            n_results: Maximo de resultados.
            min_score: Similitud minima (0-1).

        Returns:
            Lista de dicts con fact_id, text, score.
        """
        query_vec = self._embed(query)

        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                "SELECT fact_id, text, vector FROM embeddings"
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        # Calcular similitud coseno
        results = []
        for fact_id, text, blob in rows:
            stored_vec = np.frombuffer(blob, dtype=np.float32)
            score = float(np.dot(query_vec, stored_vec))
            if score >= min_score:
                results.append({
                    "fact_id": fact_id,
                    "text": text,
                    "score": round(score, 4),
                })

        # Ordenar por score descendente
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:n_results]

    def sync_from_facts(self, facts: list[dict]) -> int:
        """
        Sincroniza facts de la DB SQL al vector store.

        Args:
            facts: Lista de facts con id, subject, fact, category.

        Returns:
            Numero de facts sincronizados.
        """
        count = 0
        for f in facts:
            text = f"{f.get('category', '')} {f.get('subject', '')}: {f.get('fact', '')}"
            self.add(f["id"], text)
            count += 1

        logger.info(f"Sincronizados {count} facts al vector store.")
        return count

    def count(self) -> int:
        """Retorna el numero de embeddings almacenados."""
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM embeddings")
            return cursor.fetchone()[0]
        finally:
            conn.close()

    @property
    def is_model_ready(self) -> bool:
        """True si el modelo ONNX ya esta descargado."""
        model_path = self._model_dir / "all-MiniLM-L6-v2.onnx"
        tokenizer_path = self._model_dir / "tokenizer.json"
        return model_path.exists() and tokenizer_path.exists()
