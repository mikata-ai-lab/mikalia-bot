"""
skill_tools.py — Tools para que Mikalia cree y maneje sus propios skills.

Permite a Mikalia:
- Crear nuevos tools en Python (auto-skills)
- Listar skills custom existentes

Uso:
    from mikalia.tools.skill_tools import CreateSkillTool
    tool = CreateSkillTool(skill_creator)
    result = tool.execute(name="weather", description="...", code="...")
"""

from __future__ import annotations

from typing import Any

from mikalia.core.skill_creator import SkillCreator
from mikalia.tools.base import BaseTool, ToolResult


class CreateSkillTool(BaseTool):
    """Permite a Mikalia crear nuevos tools en Python."""

    def __init__(self, creator: SkillCreator) -> None:
        self._creator = creator

    @property
    def name(self) -> str:
        return "create_skill"

    @property
    def description(self) -> str:
        return (
            "Create a new custom tool (skill) for yourself. "
            "Write Python code that inherits from BaseTool. "
            "The tool will be saved, validated for safety, and registered "
            "so you can use it immediately. "
            "Use snake_case for the name (e.g. 'weather_check'). "
            "The code MUST have a class inheriting from BaseTool with: "
            "name, description, get_parameters(), and execute() methods. "
            "Allowed imports: json, re, datetime, time, math, hashlib, "
            "urllib, pathlib, typing, dataclasses, mikalia.*"
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Tool name in snake_case (3-30 chars). "
                        "Example: 'weather_check', 'url_shortener'"
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what the tool does",
                },
                "code": {
                    "type": "string",
                    "description": (
                        "Complete Python code for the tool. Must include: "
                        "imports, a class inheriting from BaseTool, and "
                        "name/description/get_parameters/execute methods."
                    ),
                },
            },
            "required": ["name", "description", "code"],
        }

    def execute(
        self, name: str, description: str, code: str, **_: Any
    ) -> ToolResult:
        return self._creator.create_skill(name, description, code)


class ListSkillsTool(BaseTool):
    """Lista los skills custom de Mikalia."""

    def __init__(self, creator: SkillCreator) -> None:
        self._creator = creator

    @property
    def name(self) -> str:
        return "list_skills"

    @property
    def description(self) -> str:
        return (
            "List all custom skills (tools) that you've created. "
            "Shows name, description, usage stats, and status."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def execute(self, **_: Any) -> ToolResult:
        try:
            skills = self._creator.list_custom_skills()
            if not skills:
                return ToolResult(
                    success=True,
                    output="No hay skills custom todavia. Usa create_skill para crear uno.",
                )

            lines = [f"Skills custom ({len(skills)}):"]
            for s in skills:
                status = "activo" if s["is_enabled"] else "desactivado"
                lines.append(
                    f"- {s['name']}: {s['description']} "
                    f"[{status}, usado {s['times_used']}x]"
                )
            return ToolResult(success=True, output="\n".join(lines))

        except Exception as e:
            return ToolResult(success=False, error=str(e))
