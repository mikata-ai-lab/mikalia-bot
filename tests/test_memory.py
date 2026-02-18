"""
test_memory.py — Tests para el sistema de memoria de Mikalia.

Verifica:
- Inicializacion automatica del schema
- CRUD de mensajes (conversations)
- CRUD de facts
- CRUD de sessions
- Queries de goals (seed data del schema.sql)
"""

from __future__ import annotations

import pytest
from pathlib import Path

from mikalia.core.memory import MemoryManager


SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    """MemoryManager con DB temporal."""
    db_path = tmp_path / "test_memory.db"
    return MemoryManager(db_path=str(db_path), schema_path=str(SCHEMA_PATH))


# ================================================================
# Inicializacion
# ================================================================

class TestInitialization:
    def test_auto_creates_db(self, memory, tmp_path):
        """La DB se crea automaticamente."""
        db_file = tmp_path / "test_memory.db"
        assert db_file.exists()

    def test_schema_is_idempotent(self, tmp_path):
        """Crear MemoryManager dos veces no falla."""
        db_path = tmp_path / "test.db"
        MemoryManager(str(db_path), str(SCHEMA_PATH))
        MemoryManager(str(db_path), str(SCHEMA_PATH))

    def test_seed_data_loaded(self, memory):
        """Los facts iniciales del schema.sql se cargan."""
        facts = memory.get_facts(category="personal")
        assert len(facts) > 0
        subjects = [f["subject"] for f in facts]
        assert "mikata" in subjects


# ================================================================
# Conversations
# ================================================================

class TestConversations:
    def test_add_and_get_message(self, memory):
        """Agregar y recuperar un mensaje."""
        sid = "test-session-1"
        msg_id = memory.add_message(sid, "cli", "user", "Hola Mikalia")
        assert msg_id > 0

        messages = memory.get_session_messages(sid)
        assert len(messages) == 1
        assert messages[0]["content"] == "Hola Mikalia"
        assert messages[0]["role"] == "user"

    def test_get_session_messages_ordered(self, memory):
        """Los mensajes se retornan en orden cronologico."""
        sid = "test-session-2"
        memory.add_message(sid, "cli", "user", "Primero")
        memory.add_message(sid, "cli", "assistant", "Segundo")
        memory.add_message(sid, "cli", "user", "Tercero")

        messages = memory.get_session_messages(sid)
        assert len(messages) == 3
        assert messages[0]["content"] == "Primero"
        assert messages[1]["content"] == "Segundo"
        assert messages[2]["content"] == "Tercero"

    def test_get_session_messages_with_limit(self, memory):
        """El limit funciona correctamente."""
        sid = "test-session-3"
        for i in range(10):
            memory.add_message(sid, "cli", "user", f"Msg {i}")

        messages = memory.get_session_messages(sid, limit=3)
        assert len(messages) == 3

    def test_invalid_role_rejected(self, memory):
        """Roles invalidos lanzan ValueError."""
        with pytest.raises(ValueError, match="Rol invalido"):
            memory.add_message("s1", "cli", "hacker", "bad role")

    def test_message_with_metadata(self, memory):
        """Metadata se guarda como JSON."""
        sid = "test-meta"
        memory.add_message(
            sid, "cli", "tool", "resultado",
            metadata={"tool_name": "file_read"},
        )
        messages = memory.get_session_messages(sid)
        assert messages[0]["metadata"] is not None


# ================================================================
# Facts
# ================================================================

class TestFacts:
    def test_add_and_get_fact(self, memory):
        """Agregar y recuperar un fact."""
        fact_id = memory.add_fact(
            "technical", "test", "Python es genial", source="test"
        )
        assert fact_id > 0

        facts = memory.get_facts(category="technical", subject="test")
        assert len(facts) >= 1
        assert any(f["fact"] == "Python es genial" for f in facts)

    def test_get_facts_by_category(self, memory):
        """Filtrar facts por categoria."""
        memory.add_fact("preference", "test", "Le gusta el cafe")
        facts = memory.get_facts(category="preference")
        assert all(f["category"] == "preference" for f in facts)

    def test_search_facts(self, memory):
        """Buscar facts por texto."""
        memory.add_fact("technical", "test", "SQLite es rapido y confiable")
        results = memory.search_facts("rapido")
        assert len(results) >= 1
        assert any("rapido" in r["fact"] for r in results)

    def test_deactivate_fact(self, memory):
        """Desactivar un fact (soft delete)."""
        fact_id = memory.add_fact("test", "test", "Dato temporal")
        memory.deactivate_fact(fact_id)

        facts = memory.get_facts(category="test", active_only=True)
        assert not any(f["id"] == fact_id for f in facts)

    def test_seed_facts_present(self, memory):
        """Los seed facts del schema.sql estan presentes."""
        facts = memory.get_facts()
        assert len(facts) >= 10  # schema.sql tiene 14 seed facts


# ================================================================
# Sessions
# ================================================================

class TestSessions:
    def test_create_session_returns_uuid(self, memory):
        """create_session retorna un UUID valido."""
        sid = memory.create_session("cli")
        assert len(sid) == 36  # UUID format: 8-4-4-4-12
        assert "-" in sid

    def test_get_session(self, memory):
        """Recuperar metadata de sesion."""
        sid = memory.create_session("telegram")
        session = memory.get_session(sid)
        assert session is not None
        assert session["channel"] == "telegram"

    def test_end_session(self, memory):
        """Finalizar sesion calcula duracion."""
        sid = memory.create_session("cli")
        memory.end_session(sid, summary="Test session")
        session = memory.get_session(sid)
        assert session["ended_at"] is not None
        assert session["summary"] == "Test session"

    def test_get_last_session_returns_recent(self, memory):
        """Retoma la ultima sesion activa de un canal."""
        sid = memory.create_session("telegram")
        last = memory.get_last_session("telegram")
        assert last is not None
        assert last["id"] == sid

    def test_get_last_session_ignores_ended(self, memory):
        """No retoma sesiones que ya fueron cerradas."""
        sid = memory.create_session("telegram")
        memory.end_session(sid, summary="done")
        last = memory.get_last_session("telegram")
        assert last is None

    def test_get_last_session_ignores_other_channel(self, memory):
        """No retoma sesiones de otro canal."""
        memory.create_session("cli")
        last = memory.get_last_session("telegram")
        assert last is None


# ================================================================
# Goals
# ================================================================

class TestGoals:
    def test_seed_goals_loaded(self, memory):
        """Los seed goals del schema.sql estan presentes."""
        goals = memory.get_active_goals()
        assert len(goals) >= 5  # schema.sql tiene 11 seed goals

    def test_get_active_goals_by_project(self, memory):
        """Filtrar goals por proyecto."""
        goals = memory.get_active_goals(project="mikalia-core")
        assert len(goals) >= 1
        assert all(g["project"] == "mikalia-core" for g in goals)

    def test_update_goal_progress(self, memory):
        """Actualizar progreso de un goal."""
        goals = memory.get_active_goals()
        goal_id = goals[0]["id"]

        memory.update_goal_progress(goal_id, 50, note="Avanzando bien")

        # Verificar que se actualizo
        updated = memory.get_active_goals()
        goal = next(g for g in updated if g["id"] == goal_id)
        assert goal["progress"] == 50

    def test_update_creates_goal_update_record(self, memory):
        """Actualizar progreso crea registro en goal_updates."""
        goals = memory.get_active_goals()
        goal_id = goals[0]["id"]

        memory.update_goal_progress(goal_id, 25, note="Primer avance")

        updates = memory.get_goal_updates(goal_id)
        assert len(updates) >= 1
        assert updates[0]["note"] == "Primer avance"
        assert updates[0]["new_value"] == "25"
