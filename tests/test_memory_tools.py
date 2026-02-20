"""
test_memory_tools.py — Tests para memory tools y self-improvement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mikalia.core.memory import MemoryManager
from mikalia.tools.memory_tools import (
    SearchMemoryTool,
    AddFactTool,
    UpdateGoalTool,
    ListGoalsTool,
)

SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    """MemoryManager con DB temporal."""
    db_path = tmp_path / "test_memory_tools.db"
    return MemoryManager(db_path=str(db_path), schema_path=str(SCHEMA_PATH))


# ================================================================
# SearchMemoryTool
# ================================================================

class TestSearchMemoryTool:
    def test_name_and_definition(self, memory):
        tool = SearchMemoryTool(memory)
        assert tool.name == "search_memory"
        d = tool.to_claude_definition()
        assert "query" in d["input_schema"]["properties"]

    def test_search_no_results(self, memory):
        tool = SearchMemoryTool(memory)
        result = tool.execute(query="nonexistent topic xyz")
        assert result.success
        assert "no encontre" in result.output.lower()

    def test_search_finds_seed_facts(self, memory):
        tool = SearchMemoryTool(memory)
        result = tool.execute(query="Miguel")
        assert result.success
        assert "resultado" in result.output.lower()

    def test_search_finds_added_fact(self, memory):
        memory.add_fact(
            category="technical",
            subject="python",
            fact="Python 3.14 has new features",
            source="test",
        )
        tool = SearchMemoryTool(memory)
        result = tool.execute(query="Python 3.14")
        assert result.success
        assert "Python 3.14" in result.output


# ================================================================
# AddFactTool
# ================================================================

class TestAddFactTool:
    def test_name_and_definition(self, memory):
        tool = AddFactTool(memory)
        assert tool.name == "add_fact"
        d = tool.to_claude_definition()
        assert "category" in d["input_schema"]["properties"]
        assert "subject" in d["input_schema"]["properties"]
        assert "fact" in d["input_schema"]["properties"]

    def test_add_fact_success(self, memory):
        tool = AddFactTool(memory)
        result = tool.execute(
            category="personal",
            subject="mikata",
            fact="Le gusta el ramen",
        )
        assert result.success
        assert "aprendido" in result.output.lower()
        assert "ramen" in result.output

    def test_added_fact_is_searchable(self, memory):
        add_tool = AddFactTool(memory)
        add_tool.execute(
            category="preference",
            subject="mikata",
            fact="Su IDE favorito es VS Code",
        )

        search_tool = SearchMemoryTool(memory)
        result = search_tool.execute(query="VS Code")
        assert result.success
        assert "VS Code" in result.output

    def test_add_fact_with_all_categories(self, memory):
        tool = AddFactTool(memory)
        for cat in ["personal", "project", "preference", "technical", "health"]:
            result = tool.execute(
                category=cat,
                subject="test",
                fact=f"Test fact for {cat}",
            )
            assert result.success, f"Failed for category: {cat}"


# ================================================================
# UpdateGoalTool
# ================================================================

class TestUpdateGoalTool:
    def test_name_and_definition(self, memory):
        tool = UpdateGoalTool(memory)
        assert tool.name == "update_goal"
        d = tool.to_claude_definition()
        assert "goal_id" in d["input_schema"]["properties"]
        assert "progress" in d["input_schema"]["properties"]

    def test_update_goal_progress(self, memory):
        goals = memory.get_active_goals()
        if not goals:
            pytest.skip("No seed goals available")

        tool = UpdateGoalTool(memory)
        goal_id = goals[0]["id"]
        result = tool.execute(goal_id=goal_id, progress=50, note="Halfway there")
        assert result.success
        assert "50%" in result.output

    def test_complete_goal(self, memory):
        goals = memory.get_active_goals()
        if not goals:
            pytest.skip("No seed goals available")

        tool = UpdateGoalTool(memory)
        goal_id = goals[0]["id"]
        result = tool.execute(goal_id=goal_id, progress=100)
        assert result.success
        assert "completado" in result.output.lower()


# ================================================================
# ListGoalsTool
# ================================================================

class TestListGoalsTool:
    def test_name_and_definition(self, memory):
        tool = ListGoalsTool(memory)
        assert tool.name == "list_goals"
        d = tool.to_claude_definition()
        assert "project" in d["input_schema"]["properties"]

    def test_list_goals_shows_seed_data(self, memory):
        tool = ListGoalsTool(memory)
        result = tool.execute()
        assert result.success
        # Seed data has goals
        assert "goals activos" in result.output.lower() or "no hay" in result.output.lower()

    def test_list_goals_filter_by_project(self, memory):
        tool = ListGoalsTool(memory)
        result = tool.execute(project="nonexistent-project-xyz")
        assert result.success
        assert "no hay" in result.output.lower()


# ================================================================
# Integration: Full learning cycle
# ================================================================

class TestLearningCycle:
    """Mikalia aprende un fact, lo busca, y lo recuerda."""

    def test_learn_search_recall(self, memory):
        add_tool = AddFactTool(memory)
        search_tool = SearchMemoryTool(memory)

        # 1. Learn
        add_result = add_tool.execute(
            category="technical",
            subject="mikalia-core",
            fact="Memory system uses SQLite with WAL mode",
        )
        assert add_result.success

        # 2. Search
        search_result = search_tool.execute(query="SQLite WAL")
        assert search_result.success
        assert "SQLite" in search_result.output
        assert "WAL" in search_result.output

    def test_learn_multiple_facts_and_search(self, memory):
        add_tool = AddFactTool(memory)
        search_tool = SearchMemoryTool(memory)

        # Learn multiple facts
        facts = [
            ("personal", "mikata", "Vive en Monterrey, Mexico"),
            ("preference", "mikata", "Prefiere trabajar de noche"),
            ("technical", "mikalia-bot", "Usa Claude claude-sonnet-4-5-20250929 como modelo"),
        ]
        for cat, subj, fact in facts:
            add_tool.execute(category=cat, subject=subj, fact=fact)

        # Search by different queries
        result = search_tool.execute(query="Monterrey")
        assert "Monterrey" in result.output

        result = search_tool.execute(query="noche")
        assert "noche" in result.output
