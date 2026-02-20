"""
test_daily_brief.py — Tests para DailyBriefTool.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mikalia.core.memory import MemoryManager
from mikalia.tools.daily_brief import DailyBriefTool

SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    """MemoryManager con DB temporal."""
    db_path = tmp_path / "test_brief.db"
    return MemoryManager(db_path=str(db_path), schema_path=str(SCHEMA_PATH))


class TestDailyBriefTool:
    def test_name_and_definition(self, memory):
        tool = DailyBriefTool(memory)
        assert tool.name == "daily_brief"
        d = tool.to_claude_definition()
        assert "format" in d["input_schema"]["properties"]

    def test_generates_text_brief(self, memory):
        tool = DailyBriefTool(memory)
        result = tool.execute(format="text")
        assert result.success
        assert "Buenos dias" in result.output
        assert "Goals activos" in result.output
        assert "salud" in result.output.lower()

    def test_generates_telegram_brief(self, memory):
        tool = DailyBriefTool(memory)
        result = tool.execute(format="telegram")
        assert result.success
        assert "<b>" in result.output
        assert "<i>" in result.output

    def test_includes_goals(self, memory):
        tool = DailyBriefTool(memory)
        result = tool.execute()
        assert result.success
        # Seed data tiene goals
        assert "mikalia-core" in result.output.lower() or "Goals activos" in result.output

    def test_includes_health_reminder(self, memory):
        tool = DailyBriefTool(memory)
        result = tool.execute()
        assert result.success
        assert "11pm" in result.output

    def test_progress_bar(self):
        bar = DailyBriefTool._progress_bar(50, width=10)
        assert bar == "[#####.....]"

    def test_progress_bar_empty(self):
        bar = DailyBriefTool._progress_bar(0, width=10)
        assert bar == "[..........]"

    def test_progress_bar_full(self):
        bar = DailyBriefTool._progress_bar(100, width=10)
        assert bar == "[##########]"

    def test_includes_recent_facts(self, memory):
        # Agregar un fact de conversacion
        memory.add_fact(
            category="personal",
            subject="test",
            fact="Dato de prueba",
            source="conversation",
        )
        tool = DailyBriefTool(memory)
        result = tool.execute()
        assert result.success
        assert "aprendi" in result.output.lower()
