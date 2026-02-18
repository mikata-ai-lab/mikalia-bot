"""
memory.py — Sistema de memoria persistente de Mikalia.

SQLite-based memory manager con tres capas:
1. Conversations: historial de mensajes por sesion
2. Facts: conocimiento extraido y persistente
3. Goals: tracking de objetivos y progreso
4. Sessions: metadata de sesiones de trabajo

Usa el schema definido en schema.sql para inicializar la DB.
Auto-crea data/memory.db en el primer uso.

Uso:
    from mikalia.core.memory import MemoryManager
    memory = MemoryManager("data/memory.db")
    memory.add_message("session-123", "cli", "user", "Hola Mikalia")
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.core.memory")

# Roles validos para mensajes
VALID_ROLES = ("user", "assistant", "system", "tool")


class MemoryManager:
    """
    Sistema de memoria persistente de Mikalia basado en SQLite.

    Maneja tres capas de memoria:
    - Conversations: historial raw de mensajes por sesion
    - Facts: conocimiento extraido y persistente
    - Goals: tracking de objetivos con progreso

    Args:
        db_path: Ruta a la base de datos SQLite.
        schema_path: Ruta al archivo schema.sql (auto-descubre si None).
    """

    def __init__(
        self,
        db_path: str | Path = "data/memory.db",
        schema_path: str | Path | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._schema_path = self._resolve_schema_path(schema_path)
        self._ensure_initialized()

    # ================================================================
    # Inicializacion
    # ================================================================

    def _resolve_schema_path(self, schema_path: str | Path | None) -> Path:
        """Busca schema.sql en el proyecto."""
        if schema_path:
            return Path(schema_path)

        # Buscar hacia arriba desde el paquete mikalia
        current = Path(__file__).parent.parent.parent
        candidate = current / "schema.sql"
        if candidate.exists():
            return candidate

        # Buscar desde cwd
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            candidate = parent / "schema.sql"
            if candidate.exists():
                return candidate

        raise FileNotFoundError(
            "No se encontro schema.sql. Especifica la ruta manualmente."
        )

    def _get_connection(self) -> sqlite3.Connection:
        """Crea una conexion a SQLite con row_factory."""
        conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _is_initialized(self) -> bool:
        """Verifica si el schema ya fue creado."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='conversations'"
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def _ensure_initialized(self) -> None:
        """Inicializa el schema si no existe."""
        if self._is_initialized():
            return

        logger.info(f"Inicializando memoria en {self._db_path}")
        schema_sql = self._schema_path.read_text(encoding="utf-8")

        conn = self._get_connection()
        try:
            conn.executescript(schema_sql)
            conn.commit()
            logger.success("Schema y seed data cargados")
        finally:
            conn.close()

    # ================================================================
    # Conversations
    # ================================================================

    def add_message(
        self,
        session_id: str,
        channel: str,
        role: str,
        content: str,
        metadata: dict | None = None,
        tokens_used: int = 0,
    ) -> int:
        """
        Agrega un mensaje al historial de conversacion.

        Args:
            session_id: UUID de la sesion.
            channel: Canal de origen (cli, telegram, etc.)
            role: Rol del mensaje (user, assistant, system, tool).
            content: Contenido del mensaje.
            metadata: Datos adicionales (tool_calls, etc.)
            tokens_used: Tokens consumidos.

        Returns:
            ID del mensaje insertado.
        """
        if role not in VALID_ROLES:
            raise ValueError(
                f"Rol invalido: '{role}'. Validos: {VALID_ROLES}"
            )

        meta_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO conversations "
                "(session_id, channel, role, content, metadata, tokens_used) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, channel, role, content, meta_json, tokens_used),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_session_messages(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """
        Obtiene mensajes de una sesion en orden cronologico.

        Args:
            session_id: UUID de la sesion.
            limit: Maximo de mensajes a retornar.

        Returns:
            Lista de dicts con id, role, content, metadata, created_at.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT id, session_id, channel, role, content, "
                "metadata, tokens_used, created_at "
                "FROM conversations "
                "WHERE session_id = ? "
                "ORDER BY created_at ASC "
                "LIMIT ?",
                (session_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_recent_messages(
        self,
        channel: str | None = None,
        hours: int = 24,
    ) -> list[dict]:
        """
        Obtiene mensajes recientes, opcionalmente filtrados por canal.

        Args:
            channel: Filtrar por canal (None = todos).
            hours: Ventana de tiempo en horas.

        Returns:
            Lista de mensajes recientes.
        """
        conn = self._get_connection()
        try:
            if channel:
                cursor = conn.execute(
                    "SELECT id, session_id, channel, role, content, "
                    "metadata, tokens_used, created_at "
                    "FROM conversations "
                    "WHERE channel = ? "
                    "AND created_at >= datetime('now', 'localtime', ?)"
                    "ORDER BY created_at DESC",
                    (channel, f"-{hours} hours"),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, session_id, channel, role, content, "
                    "metadata, tokens_used, created_at "
                    "FROM conversations "
                    "WHERE created_at >= datetime('now', 'localtime', ?)"
                    "ORDER BY created_at DESC",
                    (f"-{hours} hours",),
                )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ================================================================
    # Facts
    # ================================================================

    def add_fact(
        self,
        category: str,
        subject: str,
        fact: str,
        source: str | None = None,
        confidence: float = 1.0,
    ) -> int:
        """
        Agrega un fact a la memoria.

        Args:
            category: Categoria (personal, project, preference, technical, health).
            subject: Sujeto (mikata, spio, mesaflow, etc.)
            fact: El dato en si.
            source: Origen del dato.
            confidence: Confianza (0.0-1.0).

        Returns:
            ID del fact insertado.
        """
        conn = self._get_connection()
        try:
            # Deduplicacion: no guardar facts que ya existen
            existing = conn.execute(
                "SELECT id FROM facts "
                "WHERE subject = ? AND fact = ? AND is_active = 1",
                (subject, fact),
            ).fetchone()
            if existing:
                logger.info(f"Fact duplicado ignorado: {subject}: {fact[:50]}")
                return existing["id"]

            cursor = conn.execute(
                "INSERT INTO facts (category, subject, fact, source, confidence) "
                "VALUES (?, ?, ?, ?, ?)",
                (category, subject, fact, source, confidence),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_facts(
        self,
        category: str | None = None,
        subject: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """
        Obtiene facts filtrados por categoria y/o sujeto.

        Args:
            category: Filtrar por categoria (None = todas).
            subject: Filtrar por sujeto (None = todos).
            active_only: Solo facts activos (default True).

        Returns:
            Lista de facts.
        """
        conditions = []
        params: list[Any] = []

        if active_only:
            conditions.append("is_active = 1")
        if category:
            conditions.append("category = ?")
            params.append(category)
        if subject:
            conditions.append("subject = ?")
            params.append(subject)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"SELECT id, category, subject, fact, confidence, "
                f"source, is_active, created_at, updated_at "
                f"FROM facts {where} "
                f"ORDER BY created_at DESC",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_facts(self, query: str, limit: int = 10) -> list[dict]:
        """
        Busca facts por texto (LIKE simple, F1).

        Args:
            query: Texto a buscar.
            limit: Maximo de resultados.

        Returns:
            Facts que coinciden con la busqueda.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT id, category, subject, fact, confidence, "
                "source, created_at "
                "FROM facts "
                "WHERE is_active = 1 AND fact LIKE ? "
                "ORDER BY confidence DESC, created_at DESC "
                "LIMIT ?",
                (f"%{query}%", limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def deactivate_fact(self, fact_id: int) -> None:
        """Desactiva un fact (soft delete)."""
        conn = self._get_connection()
        try:
            conn.execute(
                "UPDATE facts SET is_active = 0, "
                "updated_at = datetime('now', 'localtime') "
                "WHERE id = ?",
                (fact_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ================================================================
    # Sessions
    # ================================================================

    def create_session(self, channel: str) -> str:
        """
        Crea una nueva sesion de trabajo.

        Args:
            channel: Canal de la sesion (cli, telegram, etc.)

        Returns:
            UUID de la sesion creada.
        """
        session_id = str(uuid.uuid4())
        conn = self._get_connection()
        try:
            conn.execute(
                "INSERT INTO sessions (id, channel) VALUES (?, ?)",
                (session_id, channel),
            )
            conn.commit()
            logger.info(f"Sesion creada: {session_id[:8]}... ({channel})")
            return session_id
        finally:
            conn.close()

    def end_session(
        self,
        session_id: str,
        summary: str | None = None,
    ) -> None:
        """
        Finaliza una sesion calculando duracion.

        Args:
            session_id: UUID de la sesion.
            summary: Resumen auto-generado.
        """
        conn = self._get_connection()
        try:
            conn.execute(
                "UPDATE sessions SET "
                "ended_at = datetime('now', 'localtime'), "
                "duration_minutes = CAST("
                "  (julianday('now', 'localtime') - julianday(started_at)) "
                "  * 24 * 60 AS INTEGER"
                "), "
                "summary = ? "
                "WHERE id = ?",
                (summary, session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_session(self, session_id: str) -> dict | None:
        """Obtiene metadata de una sesion."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_last_session(self, channel: str, max_age_hours: int = 6) -> dict | None:
        """
        Obtiene la ultima sesion activa de un canal (sin ended_at).

        Si la sesion es mas vieja que max_age_hours, retorna None.

        Args:
            channel: Canal a buscar (telegram, cli, etc.)
            max_age_hours: Edad maxima en horas.

        Returns:
            Dict con la sesion o None.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM sessions "
                "WHERE channel = ? "
                "AND ended_at IS NULL "
                "AND started_at >= datetime('now', 'localtime', ?) "
                "ORDER BY started_at DESC LIMIT 1",
                (channel, f"-{max_age_hours} hours"),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_session_stats(self, session_id: str) -> dict:
        """
        Obtiene estadisticas de una sesion: mensajes, tokens, herramientas.

        Returns:
            Dict con total_messages, total_tokens, user_messages, assistant_messages.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT "
                "  COUNT(*) as total_messages, "
                "  COALESCE(SUM(tokens_used), 0) as total_tokens, "
                "  SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) as user_messages, "
                "  SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages "
                "FROM conversations WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else {
                "total_messages": 0, "total_tokens": 0,
                "user_messages": 0, "assistant_messages": 0,
            }
        finally:
            conn.close()

    def get_token_usage(self, hours: int = 24) -> dict:
        """
        Obtiene uso total de tokens en las ultimas N horas.

        Returns:
            Dict con total_tokens, total_messages, sessions.
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT "
                "  COALESCE(SUM(tokens_used), 0) as total_tokens, "
                "  COUNT(*) as total_messages, "
                "  COUNT(DISTINCT session_id) as sessions "
                "FROM conversations "
                "WHERE created_at >= datetime('now', 'localtime', ?)",
                (f"-{hours} hours",),
            )
            row = cursor.fetchone()
            return dict(row) if row else {
                "total_tokens": 0, "total_messages": 0, "sessions": 0,
            }
        finally:
            conn.close()

    # ================================================================
    # Goals
    # ================================================================

    def get_active_goals(
        self,
        project: str | None = None,
    ) -> list[dict]:
        """
        Obtiene goals activos, opcionalmente filtrados por proyecto.

        Args:
            project: Filtrar por proyecto (None = todos).

        Returns:
            Lista de goals activos.
        """
        conn = self._get_connection()
        try:
            if project:
                cursor = conn.execute(
                    "SELECT id, project, title, description, status, "
                    "priority, phase, progress, due_date, created_at "
                    "FROM goals "
                    "WHERE status = 'active' AND project = ? "
                    "ORDER BY "
                    "  CASE priority "
                    "    WHEN 'critical' THEN 0 "
                    "    WHEN 'high' THEN 1 "
                    "    WHEN 'medium' THEN 2 "
                    "    WHEN 'low' THEN 3 "
                    "  END, created_at",
                    (project,),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, project, title, description, status, "
                    "priority, phase, progress, due_date, created_at "
                    "FROM goals "
                    "WHERE status = 'active' "
                    "ORDER BY "
                    "  CASE priority "
                    "    WHEN 'critical' THEN 0 "
                    "    WHEN 'high' THEN 1 "
                    "    WHEN 'medium' THEN 2 "
                    "    WHEN 'low' THEN 3 "
                    "  END, created_at",
                )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_goal_progress(
        self,
        goal_id: int,
        progress: int,
        note: str | None = None,
    ) -> None:
        """
        Actualiza el progreso de un goal y registra el cambio.

        Args:
            goal_id: ID del goal.
            progress: Nuevo progreso (0-100).
            note: Nota sobre el cambio.
        """
        conn = self._get_connection()
        try:
            # Obtener progreso actual
            cursor = conn.execute(
                "SELECT progress FROM goals WHERE id = ?",
                (goal_id,),
            )
            row = cursor.fetchone()
            old_progress = row["progress"] if row else 0

            # Actualizar goal
            status = "completed" if progress >= 100 else "active"
            conn.execute(
                "UPDATE goals SET progress = ?, status = ?, "
                "updated_at = datetime('now', 'localtime'), "
                "completed_at = CASE WHEN ? >= 100 "
                "  THEN datetime('now', 'localtime') ELSE NULL END "
                "WHERE id = ?",
                (progress, status, progress, goal_id),
            )

            # Registrar cambio en goal_updates
            conn.execute(
                "INSERT INTO goal_updates "
                "(goal_id, update_type, old_value, new_value, note) "
                "VALUES (?, 'progress', ?, ?, ?)",
                (goal_id, str(old_progress), str(progress), note),
            )
            conn.commit()
        finally:
            conn.close()

    def get_goal_updates(
        self,
        goal_id: int,
        limit: int = 10,
    ) -> list[dict]:
        """Obtiene historial de cambios de un goal."""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT id, goal_id, update_type, old_value, "
                "new_value, note, created_at "
                "FROM goal_updates "
                "WHERE goal_id = ? "
                "ORDER BY created_at DESC "
                "LIMIT ?",
                (goal_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
