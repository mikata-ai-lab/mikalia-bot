"""
test_habit_tracker.py — Tests para HabitTrackerTool.

Verifica:
- Agregar habitos
- Habitos duplicados
- Completar habitos
- Completar habito ya hecho hoy
- Listar habitos
- Stats de habitos
- Remover habitos
- Sin MemoryManager
- Definiciones Claude correctas
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mikalia.core.memory import MemoryManager
from mikalia.tools.habit_tracker import HabitTrackerTool


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    """MemoryManager con DB temporal.

    Nota: HabitTrackerTool accede a memory._get_conn() que es un alias
    interno de _get_connection(). Lo agregamos aqui para compatibilidad.
    """
    db_path = tmp_path / "test_habits.db"
    mem = MemoryManager(db_path=str(db_path), schema_path=str(SCHEMA_PATH))
    if not hasattr(mem, "_get_conn"):
        mem._get_conn = mem._get_connection
    return mem


@pytest.fixture
def tool(memory):
    """HabitTrackerTool con MemoryManager."""
    return HabitTrackerTool(memory=memory)


# ================================================================
# HabitTrackerTool — add
# ================================================================

class TestHabitAdd:
    def test_add_habit(self, tool):
        """Agregar un habito nuevo funciona."""
        result = tool.execute(action="add", habit_name="Meditar")

        assert result.success
        assert "Meditar" in result.output
        assert "diario" in result.output.lower()

    def test_add_duplicate_habit(self, tool):
        """Agregar habito duplicado retorna error."""
        tool.execute(action="add", habit_name="Leer")
        result = tool.execute(action="add", habit_name="Leer")

        assert not result.success
        assert "ya existe" in result.error.lower()

    def test_add_without_name(self, tool):
        """Agregar sin nombre retorna error."""
        result = tool.execute(action="add", habit_name="")

        assert not result.success
        assert "requerido" in result.error.lower()


# ================================================================
# HabitTrackerTool — complete
# ================================================================

class TestHabitComplete:
    def test_complete_habit(self, tool):
        """Completar un habito registra en habit_log."""
        tool.execute(action="add", habit_name="Ejercicio")
        result = tool.execute(action="complete", habit_name="Ejercicio")

        assert result.success
        assert "Ejercicio" in result.output
        assert "completado" in result.output.lower()

    def test_complete_already_done_today(self, tool):
        """Completar habito ya hecho hoy indica que ya fue completado."""
        tool.execute(action="add", habit_name="Agua")
        tool.execute(action="complete", habit_name="Agua")
        result = tool.execute(action="complete", habit_name="Agua")

        assert result.success
        assert "ya fue completado" in result.output.lower()

    def test_complete_nonexistent_habit(self, tool):
        """Completar habito inexistente retorna error."""
        result = tool.execute(action="complete", habit_name="Inexistente")

        assert not result.success
        assert "no encontrado" in result.error.lower()


# ================================================================
# HabitTrackerTool — list
# ================================================================

class TestHabitList:
    def test_list_habits(self, tool):
        """Listar habitos muestra estado de hoy."""
        tool.execute(action="add", habit_name="Leer")
        tool.execute(action="add", habit_name="Meditar")
        tool.execute(action="complete", habit_name="Leer")

        result = tool.execute(action="list")

        assert result.success
        assert "Leer" in result.output
        assert "Meditar" in result.output
        assert "[x]" in result.output  # Leer completado
        assert "[ ]" in result.output  # Meditar pendiente
        assert "Progreso" in result.output

    def test_list_empty(self, tool):
        """Listar sin habitos muestra mensaje."""
        result = tool.execute(action="list")

        assert result.success
        assert "No hay habitos" in result.output


# ================================================================
# HabitTrackerTool — stats
# ================================================================

class TestHabitStats:
    def test_stats(self, tool):
        """Stats muestra conteos y racha."""
        tool.execute(action="add", habit_name="Correr")
        tool.execute(action="complete", habit_name="Correr")

        result = tool.execute(action="stats", habit_name="Correr")

        assert result.success
        assert "Correr" in result.output
        assert "Total completados" in result.output
        assert "Ultimos 7 dias" in result.output
        assert "Ultimos 30 dias" in result.output
        assert "Racha actual" in result.output

    def test_stats_nonexistent(self, tool):
        """Stats de habito inexistente retorna error."""
        result = tool.execute(action="stats", habit_name="Fantasma")

        assert not result.success
        assert "no encontrado" in result.error.lower()


# ================================================================
# HabitTrackerTool — remove
# ================================================================

class TestHabitRemove:
    def test_remove_habit(self, tool):
        """Remover habito lo desactiva (soft delete)."""
        tool.execute(action="add", habit_name="TV")
        result = tool.execute(action="remove", habit_name="TV")

        assert result.success
        assert "desactivado" in result.output.lower()

        # No debe aparecer en list
        list_result = tool.execute(action="list")
        assert "TV" not in list_result.output

    def test_remove_nonexistent(self, tool):
        """Remover habito inexistente retorna error."""
        result = tool.execute(action="remove", habit_name="Nada")

        assert not result.success
        assert "no encontrado" in result.error.lower()


# ================================================================
# HabitTrackerTool — no memory
# ================================================================

class TestHabitNoMemory:
    def test_no_memory_error(self):
        """Sin MemoryManager retorna error descriptivo."""
        tool = HabitTrackerTool(memory=None)
        result = tool.execute(action="list")

        assert not result.success
        assert "MemoryManager" in result.error


# ================================================================
# HabitTrackerTool — metadata
# ================================================================

class TestHabitMetadata:
    def test_tool_metadata(self):
        """Definicion Claude tiene formato correcto."""
        tool = HabitTrackerTool()
        assert tool.name == "habit_tracker"
        assert "habit" in tool.description.lower()

        d = tool.to_claude_definition()
        assert d["name"] == "habit_tracker"
        assert "action" in d["input_schema"]["properties"]
        assert "habit_name" in d["input_schema"]["properties"]
        assert "action" in d["input_schema"]["required"]
