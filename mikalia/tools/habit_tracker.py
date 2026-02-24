"""
habit_tracker.py — Seguimiento de habitos para Mikalia.

Almacena habitos y su completado diario en SQLite.
Ayuda a Mikata-kun a construir rutinas saludables.
"""

from __future__ import annotations

import time
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.habit_tracker")

# SQL para crear tablas (se ejecuta si no existen)
HABITS_SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    frequency TEXT DEFAULT 'daily',
    created_at TEXT DEFAULT (datetime('now')),
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS habit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habit_id INTEGER NOT NULL,
    completed_at TEXT DEFAULT (datetime('now')),
    notes TEXT DEFAULT '',
    FOREIGN KEY (habit_id) REFERENCES habits(id)
);
"""


class HabitTrackerTool(BaseTool):
    """Tracker de habitos con registro diario."""

    def __init__(self, memory=None) -> None:
        self._memory = memory
        self._initialized = False

    @property
    def name(self) -> str:
        return "habit_tracker"

    @property
    def description(self) -> str:
        return (
            "Track daily habits. Actions: "
            "add (create new habit), "
            "complete (mark habit done today), "
            "list (show all habits with today's status), "
            "stats (show completion stats for a habit), "
            "remove (deactivate a habit). "
            "Helps build healthy routines."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: add, complete, list, stats, remove",
                    "enum": ["add", "complete", "list", "stats", "remove"],
                },
                "habit_name": {
                    "type": "string",
                    "description": "Name of the habit",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes for completion",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        habit_name: str = "",
        notes: str = "",
        **_: Any,
    ) -> ToolResult:
        if not self._memory:
            return ToolResult(
                success=False,
                error="Habit tracker necesita MemoryManager para funcionar",
            )

        self._ensure_tables()

        if action == "add":
            return self._add(habit_name)
        elif action == "complete":
            return self._complete(habit_name, notes)
        elif action == "list":
            return self._list()
        elif action == "stats":
            return self._stats(habit_name)
        elif action == "remove":
            return self._remove(habit_name)
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _ensure_tables(self) -> None:
        """Crea las tablas si no existen."""
        if self._initialized:
            return
        conn = self._memory._get_conn()
        conn.executescript(HABITS_SCHEMA)
        conn.commit()
        self._initialized = True

    def _add(self, name: str) -> ToolResult:
        if not name:
            return ToolResult(success=False, error="Nombre del habito requerido")

        conn = self._memory._get_conn()
        try:
            conn.execute("INSERT INTO habits (name) VALUES (?)", (name,))
            conn.commit()
            logger.success(f"Habito creado: {name}")
            return ToolResult(
                success=True,
                output=f"Habito creado: {name}\nFrecuencia: diario",
            )
        except Exception:
            return ToolResult(success=False, error=f"El habito '{name}' ya existe")

    def _complete(self, name: str, notes: str) -> ToolResult:
        if not name:
            return ToolResult(success=False, error="Nombre del habito requerido")

        conn = self._memory._get_conn()
        row = conn.execute(
            "SELECT id FROM habits WHERE name = ? AND active = 1", (name,)
        ).fetchone()

        if not row:
            return ToolResult(success=False, error=f"Habito no encontrado: {name}")

        # Verificar si ya se completo hoy
        today = conn.execute(
            "SELECT id FROM habit_log WHERE habit_id = ? AND date(completed_at) = date('now')",
            (row[0],),
        ).fetchone()

        if today:
            return ToolResult(
                success=True,
                output=f"'{name}' ya fue completado hoy!",
            )

        conn.execute(
            "INSERT INTO habit_log (habit_id, notes) VALUES (?, ?)",
            (row[0], notes),
        )
        conn.commit()

        # Contar racha
        streak = self._get_streak(conn, row[0])

        logger.success(f"Habito completado: {name} (racha: {streak})")
        return ToolResult(
            success=True,
            output=f"Habito completado: {name}\nRacha actual: {streak} dias",
        )

    def _list(self) -> ToolResult:
        conn = self._memory._get_conn()
        habits = conn.execute(
            "SELECT id, name FROM habits WHERE active = 1 ORDER BY name"
        ).fetchall()

        if not habits:
            return ToolResult(success=True, output="No hay habitos registrados.")

        lines = ["Habitos de hoy:"]
        for habit_id, name in habits:
            done = conn.execute(
                "SELECT id FROM habit_log WHERE habit_id = ? AND date(completed_at) = date('now')",
                (habit_id,),
            ).fetchone()
            status = "[x]" if done else "[ ]"
            streak = self._get_streak(conn, habit_id)
            lines.append(f"  {status} {name} (racha: {streak}d)")

        completed = sum(1 for _, n in habits if conn.execute(
            "SELECT id FROM habit_log WHERE habit_id = ? AND date(completed_at) = date('now')",
            (_,),
        ).fetchone())
        lines.append(f"\nProgreso hoy: {completed}/{len(habits)}")

        return ToolResult(success=True, output="\n".join(lines))

    def _stats(self, name: str) -> ToolResult:
        if not name:
            return ToolResult(success=False, error="Nombre del habito requerido")

        conn = self._memory._get_conn()
        row = conn.execute(
            "SELECT id, created_at FROM habits WHERE name = ?", (name,)
        ).fetchone()

        if not row:
            return ToolResult(success=False, error=f"Habito no encontrado: {name}")

        total = conn.execute(
            "SELECT COUNT(*) FROM habit_log WHERE habit_id = ?", (row[0],)
        ).fetchone()[0]

        last_7 = conn.execute(
            "SELECT COUNT(*) FROM habit_log WHERE habit_id = ? AND completed_at >= datetime('now', '-7 days')",
            (row[0],),
        ).fetchone()[0]

        last_30 = conn.execute(
            "SELECT COUNT(*) FROM habit_log WHERE habit_id = ? AND completed_at >= datetime('now', '-30 days')",
            (row[0],),
        ).fetchone()[0]

        streak = self._get_streak(conn, row[0])

        return ToolResult(
            success=True,
            output=(
                f"Stats para '{name}':\n"
                f"  Total completados: {total}\n"
                f"  Ultimos 7 dias: {last_7}/7\n"
                f"  Ultimos 30 dias: {last_30}/30\n"
                f"  Racha actual: {streak} dias\n"
                f"  Creado: {row[1]}"
            ),
        )

    def _remove(self, name: str) -> ToolResult:
        if not name:
            return ToolResult(success=False, error="Nombre del habito requerido")

        conn = self._memory._get_conn()
        result = conn.execute(
            "UPDATE habits SET active = 0 WHERE name = ? AND active = 1", (name,)
        )
        conn.commit()

        if result.rowcount == 0:
            return ToolResult(success=False, error=f"Habito no encontrado: {name}")

        return ToolResult(success=True, output=f"Habito desactivado: {name}")

    def _get_streak(self, conn: Any, habit_id: int) -> int:
        """Calcula la racha actual de dias consecutivos."""
        rows = conn.execute(
            "SELECT DISTINCT date(completed_at) as d FROM habit_log "
            "WHERE habit_id = ? ORDER BY d DESC",
            (habit_id,),
        ).fetchall()

        if not rows:
            return 0

        from datetime import datetime, timedelta
        streak = 0
        expected = datetime.now().date()

        for (date_str,) in rows:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            elif d == expected - timedelta(days=1):
                # Si hoy no se ha completado, empezar desde ayer
                if streak == 0:
                    streak = 1
                    expected = d - timedelta(days=1)
                else:
                    break
            else:
                break

        return streak
