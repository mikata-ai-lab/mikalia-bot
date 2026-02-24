"""
conversation_analytics.py — Analitica de conversaciones para Mikalia.

Analiza el historial de conversaciones almacenado en SQLite:
- Mensajes por dia/hora
- Temas mas frecuentes
- Uso de herramientas
- Sentiment basico
"""

from __future__ import annotations

from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.conversation_analytics")


class ConversationAnalyticsTool(BaseTool):
    """Analiza el historial de conversaciones de Mikalia."""

    def __init__(self, memory=None) -> None:
        self._memory = memory

    @property
    def name(self) -> str:
        return "conversation_analytics"

    @property
    def description(self) -> str:
        return (
            "Analyze conversation history. Shows: "
            "message counts, most active hours, "
            "tool usage stats, topic frequency, "
            "and conversation summaries. "
            "Use to understand usage patterns."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "report_type": {
                    "type": "string",
                    "description": "Type: overview, tools, activity, topics",
                    "enum": ["overview", "tools", "activity", "topics"],
                },
                "days": {
                    "type": "integer",
                    "description": "Days to analyze (default: 7)",
                },
            },
            "required": ["report_type"],
        }

    def execute(
        self,
        report_type: str,
        days: int = 7,
        **_: Any,
    ) -> ToolResult:
        if not self._memory:
            return ToolResult(
                success=False,
                error="Conversation analytics necesita MemoryManager",
            )

        days = max(1, min(days, 365))

        if report_type == "overview":
            return self._overview(days)
        elif report_type == "tools":
            return self._tool_usage(days)
        elif report_type == "activity":
            return self._activity(days)
        elif report_type == "topics":
            return self._topics(days)
        else:
            return ToolResult(success=False, error=f"Tipo desconocido: {report_type}")

    def _overview(self, days: int) -> ToolResult:
        conn = self._memory._get_conn()

        total_msgs = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()[0]

        total_sessions = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM conversations "
            "WHERE created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()[0]

        user_msgs = conn.execute(
            "SELECT COUNT(*) FROM conversations "
            "WHERE role = 'user' AND created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()[0]

        assistant_msgs = conn.execute(
            "SELECT COUNT(*) FROM conversations "
            "WHERE role = 'assistant' AND created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()[0]

        total_facts = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        total_goals = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE status = 'active'"
        ).fetchone()[0]

        return ToolResult(
            success=True,
            output=(
                f"=== Resumen (ultimos {days} dias) ===\n"
                f"Total mensajes: {total_msgs}\n"
                f"Sesiones: {total_sessions}\n"
                f"Mensajes de usuario: {user_msgs}\n"
                f"Mensajes de Mikalia: {assistant_msgs}\n"
                f"Ratio respuesta: {assistant_msgs / max(user_msgs, 1):.1f}x\n"
                f"\n=== Base de conocimiento ===\n"
                f"Facts almacenados: {total_facts}\n"
                f"Goals activos: {total_goals}"
            ),
        )

    def _tool_usage(self, days: int) -> ToolResult:
        conn = self._memory._get_conn()

        # Buscar mensajes de tool_use en conversaciones
        rows = conn.execute(
            "SELECT content FROM conversations "
            "WHERE role = 'assistant' AND created_at >= datetime('now', ?) "
            "AND content LIKE '%tool_use%'",
            (f"-{days} days",),
        ).fetchall()

        tool_counts: dict[str, int] = {}
        import json
        for (content,) in rows:
            try:
                blocks = json.loads(content) if content.startswith("[") else []
                for block in blocks:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = block.get("name", "unknown")
                        tool_counts[name] = tool_counts.get(name, 0) + 1
            except (json.JSONDecodeError, TypeError):
                continue

        if not tool_counts:
            return ToolResult(
                success=True,
                output=f"No se encontraron usos de herramientas en los ultimos {days} dias.",
            )

        sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)
        lines = [f"=== Uso de herramientas (ultimos {days} dias) ==="]
        for name, count in sorted_tools:
            bar = "#" * min(count, 20)
            lines.append(f"  {name}: {count} {bar}")

        lines.append(f"\nTotal invocaciones: {sum(tool_counts.values())}")
        lines.append(f"Herramientas distintas: {len(tool_counts)}")

        return ToolResult(success=True, output="\n".join(lines))

    def _activity(self, days: int) -> ToolResult:
        conn = self._memory._get_conn()

        # Mensajes por dia
        daily = conn.execute(
            "SELECT date(created_at) as d, COUNT(*) as c "
            "FROM conversations WHERE created_at >= datetime('now', ?) "
            "GROUP BY d ORDER BY d DESC",
            (f"-{days} days",),
        ).fetchall()

        if not daily:
            return ToolResult(
                success=True,
                output=f"No hay actividad en los ultimos {days} dias.",
            )

        lines = [f"=== Actividad diaria (ultimos {days} dias) ==="]
        for date_str, count in daily:
            bar = "#" * min(count, 30)
            lines.append(f"  {date_str}: {count:3d} {bar}")

        # Promedio
        avg = sum(c for _, c in daily) / len(daily)
        lines.append(f"\nPromedio: {avg:.1f} mensajes/dia")

        return ToolResult(success=True, output="\n".join(lines))

    def _topics(self, days: int) -> ToolResult:
        conn = self._memory._get_conn()

        # Analizar facts por categoria
        categories = conn.execute(
            "SELECT category, COUNT(*) as c FROM facts "
            "GROUP BY category ORDER BY c DESC"
        ).fetchall()

        lines = ["=== Temas por categoria (facts) ==="]
        for cat, count in categories:
            lines.append(f"  {cat}: {count}")

        # Ultimos temas de conversacion (subjects de facts recientes)
        recent = conn.execute(
            "SELECT subject, fact FROM facts "
            "WHERE created_at >= datetime('now', ?) "
            "ORDER BY created_at DESC LIMIT 10",
            (f"-{days} days",),
        ).fetchall()

        if recent:
            lines.append(f"\n=== Temas recientes (ultimos {days} dias) ===")
            for subject, fact in recent:
                lines.append(f"  - {subject}: {fact[:60]}")

        return ToolResult(success=True, output="\n".join(lines))
