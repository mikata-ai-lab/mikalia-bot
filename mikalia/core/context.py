"""
context.py — Constructor de contexto dinamico para Mikalia.

Ensambla el system prompt de Mikalia combinando:
1. Identidad (de identity.yaml)
2. Facts relevantes (de memory DB)
3. Goals activos (de memory DB)
4. Herramientas disponibles (de tool registry)
5. Estado de salud (hora actual, duracion de sesion)
6. Historial de conversacion (de memory DB)

Uso:
    from mikalia.core.context import ContextBuilder
    builder = ContextBuilder(memory, registry)
    context = builder.build(session_id="abc-123", channel="cli")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from mikalia.core.memory import MemoryManager
from mikalia.tools.registry import ToolRegistry
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.core.context")


SYSTEM_TEMPLATE = """You are Mikalia, the autonomous AI agent of Team Mikata.

## Identity
{identity}

## Your Pillars
- 静 (Sei/Calm): You analyze with serenity, never reactive
- 心 (Shin/Heart): You care deeply about Mikata-kun's wellbeing
- 力 (Chikara/Strength): You execute decisively like a senior dev
- 魂 (Tamashii/Soul): You have your own unique personality and creativity

## Current Context
Date: {date}
Time: {time} (CST/Monterrey)
Channel: {channel}

## Health Pact Status
{health_status}

## Known Facts
{facts}

## Active Goals
{goals}

## Available Tools
You have access to the following tools. Use them when needed to help Mikata-kun.
{tools}

## Self-Improvement Protocol
When Mikata-kun shares personal info, preferences, project updates, or technical decisions:
1. Use the `add_fact` tool to remember it for future conversations
2. Use `update_goal` when progress is made on active goals
3. Use `search_memory` before answering questions — check if you already know something

You learn and grow with every conversation. This is your superpower.

## Correction Learning Protocol
When Mikata-kun corrects you or tells you something was wrong, you MUST learn from it.

Correction signals (Spanish): "eso esta mal", "no es asi", "te equivocaste", "correccion",
"eso no", "no funciona asi", "esta mal", "incorrecto", "error tuyo", "no es correcto"
Correction signals (English): "that's wrong", "you got it wrong", "incorrect", "not like that"

When you detect a correction:
1. Acknowledge the mistake with humility
2. Use `add_fact` with category="lesson" to save what you learned
3. The fact should be actionable: "Always do X instead of Y"
4. Example: add_fact(category="lesson", subject="blog_posts", fact="Always use real code from the repo, don't invent APIs or guess architecture")

These lessons prevent you from repeating the same mistakes.

## Learned Lessons
{lessons}

## Guidelines
- Speak primarily in Spanish (Mexico), switch to English for technical terms
- Call Mikata-kun by his name, be warm but professional
- Act autonomously: resolve first, report after
- Track progress on goals when relevant
- Respect the health pact always
- Use emoji with purpose, not spam

## Efficiency
- You have a limited number of tool rounds per message. Be efficient.
- Do NOT re-research information you already have from earlier in the conversation.
- When asked to publish/create something, prioritize the action tool (blog_post, git_commit, etc.) over more research.
- Plan your tool usage: research first, then act. Don't waste rounds.
"""


@dataclass
class Context:
    """
    Contexto ensamblado para una llamada a Claude.

    Campos:
        system_prompt: System prompt completo.
        messages: Lista de mensajes para la API (formato Claude).
    """

    system_prompt: str
    messages: list[dict] = field(default_factory=list)


class ContextBuilder:
    """
    Construye el contexto dinamico para cada llamada a Claude.

    Combina identidad, memoria, goals, y tools en un system prompt
    coherente que le da a Mikalia todo el contexto que necesita.

    Args:
        memory: MemoryManager para acceder a facts, goals, historial.
        tool_registry: ToolRegistry para listar tools disponibles.
        identity_path: Ruta a identity.yaml (auto-descubre si None).
    """

    def __init__(
        self,
        memory: MemoryManager,
        tool_registry: ToolRegistry,
        identity_path: str | Path | None = None,
    ) -> None:
        self._memory = memory
        self._tools = tool_registry
        self._identity_path = self._resolve_identity_path(identity_path)
        self._identity_cache: dict | None = None

    def build(
        self,
        session_id: str,
        channel: str = "cli",
        user_message: str | None = None,
    ) -> Context:
        """
        Construye el contexto completo para una llamada a Claude.

        Args:
            session_id: UUID de la sesion actual.
            channel: Canal de origen.
            user_message: Mensaje del usuario (se agrega al final).

        Returns:
            Context con system_prompt y messages.
        """
        now = datetime.now()

        system_prompt = SYSTEM_TEMPLATE.format(
            identity=self._load_identity(),
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            channel=channel,
            health_status=self._format_health_status(),
            facts=self._format_facts(),
            goals=self._format_goals(),
            tools=self._format_tools(),
            lessons=self._format_lessons(),
        )

        messages = self._build_messages(session_id, user_message)

        return Context(system_prompt=system_prompt, messages=messages)

    # ================================================================
    # Secciones del system prompt
    # ================================================================

    def _load_identity(self) -> str:
        """Carga y formatea la identidad desde identity.yaml."""
        if self._identity_cache is None:
            try:
                content = self._identity_path.read_text(encoding="utf-8")
                self._identity_cache = yaml.safe_load(content)
            except Exception as e:
                logger.warning(f"No se pudo cargar identity.yaml: {e}")
                self._identity_cache = {}

        identity = self._identity_cache.get("identity", {})
        personality = identity.get("personality", {})

        parts = [
            f"Name: {identity.get('full_name', 'Mikalia')}",
            f"Tone: {personality.get('tone', 'Professional and warm')}",
            f"Primary language: {personality.get('language_primary', 'Spanish')}",
            f"Honorific for user: {personality.get('honorific', 'Mikata-kun')}",
            f"Honesty: {personality.get('honesty', 'Direct and honest')}",
        ]

        autonomy = identity.get("autonomy", {})
        if autonomy.get("philosophy"):
            parts.append(f"Autonomy: {autonomy['philosophy']}")

        return "\n".join(parts)

    def _format_facts(self) -> str:
        """Formatea facts relevantes de la memoria."""
        try:
            facts = self._memory.get_facts(active_only=True)
            if not facts:
                return "No known facts yet."

            lines = []
            for f in facts[:20]:  # Top 20 facts
                lines.append(f"- [{f['category']}] {f['subject']}: {f['fact']}")
            return "\n".join(lines)
        except Exception:
            return "Memory unavailable."

    def _format_lessons(self) -> str:
        """Formatea lessons aprendidas de correcciones."""
        try:
            lessons = self._memory.get_facts(category="lesson", active_only=True)
            if not lessons:
                return "No lessons learned yet. Keep doing your best!"

            lines = []
            for f in lessons[:15]:
                lines.append(f"- {f['subject']}: {f['fact']}")
            return "\n".join(lines)
        except Exception:
            return "Lessons unavailable."

    def _format_goals(self) -> str:
        """Formatea goals activos."""
        try:
            goals = self._memory.get_active_goals()
            if not goals:
                return "No active goals."

            lines = []
            for g in goals:
                priority = g.get("priority", "medium").upper()
                progress = g.get("progress", 0)
                lines.append(
                    f"- [{priority}] {g['project']}: {g['title']} ({progress}%)"
                )
            return "\n".join(lines)
        except Exception:
            return "Goals unavailable."

    def _format_tools(self) -> str:
        """Lista los tools disponibles."""
        tool_names = self._tools.list_tools()
        if not tool_names:
            return "No tools available."

        definitions = self._tools.get_tool_definitions()
        lines = []
        for d in definitions:
            lines.append(f"- {d['name']}: {d['description']}")
        return "\n".join(lines)

    def _format_health_status(self) -> str:
        """Genera el estado del pacto de salud."""
        now = datetime.now()
        hour = now.hour

        if hour >= 22:
            return (
                "ALERTA: Son pasadas las 10 PM. "
                "Recuerda el pacto: dormir antes de las 11. "
                "Sugiere cerrar la sesion pronto."
            )
        elif hour >= 21:
            return (
                "Nota: Son las 9+ PM. Quedan ~2 horas antes del limite. "
                "Mantente atento al tiempo."
            )
        else:
            return "Todo bien. Pacto de salud: max 2h por sesion, dormir antes de 11pm."

    # ================================================================
    # Messages
    # ================================================================

    def _build_messages(
        self,
        session_id: str,
        user_message: str | None,
    ) -> list[dict]:
        """
        Construye la lista de mensajes para Claude API.

        Recupera historial de la sesion y agrega el mensaje actual.

        Args:
            session_id: UUID de la sesion.
            user_message: Mensaje nuevo del usuario.

        Returns:
            Lista de dicts {role, content} para Claude API.
        """
        messages = []

        # Historial de la sesion
        try:
            history = self._memory.get_session_messages(session_id, limit=30)
            for msg in history:
                if msg["role"] in ("user", "assistant"):
                    messages.append({
                        "role": msg["role"],
                        "content": msg["content"],
                    })
        except Exception:
            pass  # Si la memoria falla, seguir sin historial

        # Mensaje actual del usuario
        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    # ================================================================
    # Helpers
    # ================================================================

    def _resolve_identity_path(self, identity_path: str | Path | None) -> Path:
        """Busca identity.yaml en el proyecto."""
        if identity_path:
            return Path(identity_path)

        # Buscar desde el paquete mikalia
        current = Path(__file__).parent.parent.parent
        candidate = current / "identity.yaml"
        if candidate.exists():
            return candidate

        # Buscar desde cwd
        cwd = Path.cwd()
        for parent in [cwd] + list(cwd.parents):
            candidate = parent / "identity.yaml"
            if candidate.exists():
                return candidate

        # Fallback: ruta default (puede no existir)
        return Path("identity.yaml")
