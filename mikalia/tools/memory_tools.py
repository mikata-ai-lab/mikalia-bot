"""
memory_tools.py — Tools para que Mikalia maneje su propia memoria.

Permite a Mikalia:
- Buscar en su memoria (facts conocidos)
- Aprender cosas nuevas (agregar facts)
- Actualizar progreso de goals
- Ver goals activos

Uso:
    from mikalia.tools.memory_tools import SearchMemoryTool
    tool = SearchMemoryTool(memory_manager)
    result = tool.execute(query="Python")
"""

from __future__ import annotations

from typing import Any

from mikalia.core.memory import MemoryManager
from mikalia.tools.base import BaseTool, ToolResult


class SearchMemoryTool(BaseTool):
    """Busca en la memoria de Mikalia — semantica + SQL."""

    def __init__(
        self,
        memory: MemoryManager,
        vector_memory: Any | None = None,
    ) -> None:
        self._memory = memory
        self._vector = vector_memory

    @property
    def name(self) -> str:
        return "search_memory"

    @property
    def description(self) -> str:
        return (
            "Search Mikalia's memory for known facts by meaning. "
            "Uses semantic search (understands context, not just keywords). "
            "Use this to recall information about Mikata-kun, projects, "
            "preferences, or any previously learned knowledge."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in memory (searches by meaning)",
                },
            },
            "required": ["query"],
        }

    def execute(self, query: str, **_: Any) -> ToolResult:
        try:
            results = []

            # 1. Busqueda semantica (si disponible)
            if self._vector is not None:
                try:
                    semantic = self._vector.search(query, n_results=5)
                    for r in semantic:
                        results.append({
                            "text": r["text"],
                            "score": r["score"],
                            "source": "semantic",
                        })
                except Exception:
                    pass  # Fallback a SQL si falla

            # 2. Busqueda SQL (siempre como complemento)
            facts = self._memory.search_facts(query, limit=10)
            for f in facts:
                text = f"[{f['category']}] {f['subject']}: {f['fact']}"
                # Evitar duplicados con resultados semanticos
                if not any(r["text"].endswith(f["fact"]) for r in results):
                    results.append({
                        "text": text,
                        "score": 0.0,
                        "source": "sql",
                    })

            if not results:
                return ToolResult(
                    success=True,
                    output=f"No encontre nada sobre '{query}' en mi memoria.",
                )

            # Ordenar: semanticos primero (por score), SQL despues
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:10]

            lines = [f"Encontre {len(results)} resultado(s):"]
            for r in results:
                prefix = f"[{r['score']:.0%}] " if r["score"] > 0 else ""
                lines.append(f"- {prefix}{r['text']}")
            return ToolResult(success=True, output="\n".join(lines))

        except Exception as e:
            return ToolResult(success=False, error=str(e))


class AddFactTool(BaseTool):
    """Permite a Mikalia aprender y recordar cosas nuevas."""

    def __init__(
        self,
        memory: MemoryManager,
        vector_memory: Any | None = None,
    ) -> None:
        self._memory = memory
        self._vector = vector_memory

    @property
    def name(self) -> str:
        return "add_fact"

    @property
    def description(self) -> str:
        return (
            "Learn and remember a new fact. Use this when Mikata-kun tells you "
            "something important about himself, his projects, preferences, or "
            "any information worth remembering for future conversations. "
            "Categories: personal, project, preference, technical, health, lesson. "
            "Use 'lesson' when you learn from a correction or mistake."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category: personal, project, preference, technical, health, lesson",
                    "enum": ["personal", "project", "preference", "technical", "health", "lesson"],
                },
                "subject": {
                    "type": "string",
                    "description": "Who/what this fact is about (e.g. 'mikata', 'spio', 'mikalia-core')",
                },
                "fact": {
                    "type": "string",
                    "description": "The fact to remember",
                },
            },
            "required": ["category", "subject", "fact"],
        }

    def execute(
        self, category: str, subject: str, fact: str, **_: Any
    ) -> ToolResult:
        try:
            fact_id = self._memory.add_fact(
                category=category,
                subject=subject,
                fact=fact,
                source="conversation",
                confidence=0.9,
            )

            # Indexar en vector store si disponible
            if self._vector is not None:
                try:
                    text = f"{category} {subject}: {fact}"
                    self._vector.add(fact_id, text)
                except Exception:
                    pass  # No bloquear si vector falla

            return ToolResult(
                success=True,
                output=f"Aprendido y guardado (fact #{fact_id}): [{category}] {subject}: {fact}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class UpdateGoalTool(BaseTool):
    """Permite a Mikalia actualizar el progreso de goals."""

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    @property
    def name(self) -> str:
        return "update_goal"

    @property
    def description(self) -> str:
        return (
            "Update the progress of an active goal. Use this when work is done "
            "on a goal or when Mikata-kun reports progress. "
            "Progress is 0-100 (100 = completed)."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal_id": {
                    "type": "integer",
                    "description": "ID of the goal to update",
                },
                "progress": {
                    "type": "integer",
                    "description": "New progress value (0-100)",
                },
                "note": {
                    "type": "string",
                    "description": "Note about the update",
                },
            },
            "required": ["goal_id", "progress"],
        }

    def execute(
        self, goal_id: int, progress: int, note: str = "", **_: Any
    ) -> ToolResult:
        try:
            self._memory.update_goal_progress(goal_id, progress, note or None)
            status = "Completado!" if progress >= 100 else f"{progress}%"
            return ToolResult(
                success=True,
                output=f"Goal #{goal_id} actualizado a {status}" + (f" — {note}" if note else ""),
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListGoalsTool(BaseTool):
    """Muestra los goals activos de Mikalia."""

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    @property
    def name(self) -> str:
        return "list_goals"

    @property
    def description(self) -> str:
        return (
            "List all active goals and their progress. "
            "Optionally filter by project name."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Filter by project (optional)",
                },
            },
            "required": [],
        }

    def execute(self, project: str = "", **_: Any) -> ToolResult:
        try:
            goals = self._memory.get_active_goals(
                project=project if project else None
            )
            if not goals:
                return ToolResult(
                    success=True,
                    output="No hay goals activos" + (f" para '{project}'" if project else ""),
                )

            lines = [f"Goals activos ({len(goals)}):"]
            for g in goals:
                lines.append(
                    f"- #{g['id']} [{g['priority'].upper()}] "
                    f"{g['project']}: {g['title']} ({g['progress']}%)"
                )
            return ToolResult(success=True, output="\n".join(lines))

        except Exception as e:
            return ToolResult(success=False, error=str(e))
