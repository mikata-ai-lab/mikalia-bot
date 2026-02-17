"""
daily_brief.py — Tool para generar el resumen diario de Mikalia.

Compila informacion de goals, facts recientes, y sesiones
para generar un brief que se puede enviar por Telegram.

Uso:
    from mikalia.tools.daily_brief import DailyBriefTool
    tool = DailyBriefTool(memory)
    result = tool.execute()
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mikalia.core.memory import MemoryManager
from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.daily_brief")


class DailyBriefTool(BaseTool):
    """Genera un resumen diario con goals, facts, y estadisticas."""

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    @property
    def name(self) -> str:
        return "daily_brief"

    @property
    def description(self) -> str:
        return (
            "Generate a daily briefing with active goals progress, "
            "recently learned facts, and session statistics. "
            "Use this to give Mikata-kun his morning update."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Output format: 'text' for plain text, 'telegram' for HTML",
                    "default": "text",
                },
            },
            "required": [],
        }

    def execute(self, format: str = "text", **_: Any) -> ToolResult:
        try:
            now = datetime.now()
            is_telegram = format == "telegram"

            sections = []

            # Header
            if is_telegram:
                sections.append(
                    f"<b>Buenos dias Mikata-kun~</b>\n"
                    f"<i>{now.strftime('%A %d de %B, %Y')}</i>\n"
                )
            else:
                sections.append(
                    f"Buenos dias Mikata-kun~\n"
                    f"{now.strftime('%A %d de %B, %Y')}\n"
                )

            # Goals
            goals = self._memory.get_active_goals()
            if goals:
                if is_telegram:
                    lines = ["<b>Goals activos:</b>"]
                else:
                    lines = ["Goals activos:"]

                for g in goals:
                    bar = self._progress_bar(g["progress"])
                    priority = g.get("priority", "medium").upper()
                    lines.append(
                        f"  [{priority}] {g['project']}: {g['title']}\n"
                        f"  {bar} {g['progress']}%"
                    )
                sections.append("\n".join(lines))

            # Recent facts
            facts = self._memory.get_facts(active_only=True)
            recent_facts = [
                f for f in facts
                if f.get("source") == "conversation"
            ][:5]

            if recent_facts:
                if is_telegram:
                    lines = ["<b>Cosas que aprendi recientemente:</b>"]
                else:
                    lines = ["Cosas que aprendi recientemente:"]

                for f in recent_facts:
                    lines.append(f"  - {f['subject']}: {f['fact'][:80]}")
                sections.append("\n".join(lines))

            # Session stats
            conn = self._memory._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) as total, "
                    "SUM(tokens_used) as tokens "
                    "FROM conversations "
                    "WHERE created_at >= date('now', '-1 day')"
                )
                row = cursor.fetchone()
                msg_count = row["total"] or 0
                token_count = row["tokens"] or 0
            finally:
                conn.close()

            if msg_count > 0:
                if is_telegram:
                    sections.append(
                        f"<b>Ultimas 24h:</b>\n"
                        f"  Mensajes: {msg_count}\n"
                        f"  Tokens: {token_count:,}"
                    )
                else:
                    sections.append(
                        f"Ultimas 24h:\n"
                        f"  Mensajes: {msg_count}\n"
                        f"  Tokens: {token_count:,}"
                    )

            # Health reminder
            if is_telegram:
                sections.append(
                    "<i>Recuerda: max 2h por sesion, dormir antes de 11pm. "
                    "Tu salud es lo primero~</i>"
                )
            else:
                sections.append(
                    "Recuerda: max 2h por sesion, dormir antes de 11pm. "
                    "Tu salud es lo primero~"
                )

            output = "\n\n".join(sections)
            return ToolResult(success=True, output=output)

        except Exception as e:
            logger.error(f"Error generando daily brief: {e}")
            return ToolResult(success=False, error=str(e))

    @staticmethod
    def _progress_bar(progress: int, width: int = 10) -> str:
        """Genera una barra de progreso visual."""
        filled = int(width * progress / 100)
        empty = width - filled
        return "[" + "#" * filled + "." * empty + "]"
