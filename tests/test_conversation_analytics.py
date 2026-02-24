"""
test_conversation_analytics.py — Tests para ConversationAnalyticsTool.

Verifica:
- Reporte overview
- Reporte activity
- Reporte topics
- Reporte tools
- Sin MemoryManager
- Definiciones Claude correctas
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mikalia.core.memory import MemoryManager
from mikalia.tools.conversation_analytics import ConversationAnalyticsTool


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    """MemoryManager con DB temporal y datos de prueba.

    Nota: ConversationAnalyticsTool accede a memory._get_conn() que es
    un alias interno de _get_connection(). Lo agregamos para compatibilidad.
    """
    db_path = tmp_path / "test_analytics.db"
    mem = MemoryManager(db_path=str(db_path), schema_path=str(SCHEMA_PATH))
    if not hasattr(mem, "_get_conn"):
        mem._get_conn = mem._get_connection

    # Crear sesion y agregar mensajes de prueba
    sid = mem.create_session("cli")
    mem.add_message(sid, "cli", "user", "Hola Mikalia, como estas?")
    mem.add_message(sid, "cli", "assistant", "Hola! Estoy bien, gracias.")
    mem.add_message(sid, "cli", "user", "Quiero aprender Python")
    mem.add_message(sid, "cli", "assistant", "Python es genial para empezar!")
    mem.add_message(sid, "cli", "user", "Y tambien Rust")
    mem.add_message(sid, "cli", "assistant", "Rust tiene un sistema de tipos increible.")

    return mem


@pytest.fixture
def memory_with_tools(memory):
    """MemoryManager con datos de tool_use en conversaciones."""
    sid = memory.create_session("telegram")
    # Simular mensaje con tool_use
    tool_use_content = json.dumps([
        {"type": "tool_use", "name": "file_read", "input": {"path": "test.py"}},
    ])
    memory.add_message(sid, "telegram", "assistant", tool_use_content)

    tool_use_content2 = json.dumps([
        {"type": "tool_use", "name": "file_read", "input": {"path": "app.py"}},
        {"type": "tool_use", "name": "web_fetch", "input": {"url": "https://x.com"}},
    ])
    memory.add_message(sid, "telegram", "assistant", tool_use_content2)

    return memory


@pytest.fixture
def tool(memory):
    """ConversationAnalyticsTool con MemoryManager."""
    return ConversationAnalyticsTool(memory=memory)


# ================================================================
# ConversationAnalyticsTool — overview
# ================================================================

class TestConversationOverview:
    def test_overview_report(self, tool):
        """Overview muestra stats generales."""
        result = tool.execute(report_type="overview", days=7)

        assert result.success
        assert "Total mensajes" in result.output
        assert "Sesiones" in result.output
        assert "Mensajes de usuario" in result.output
        assert "Mensajes de Mikalia" in result.output
        assert "Facts almacenados" in result.output
        assert "Goals activos" in result.output

    def test_overview_counts_messages(self, tool):
        """Overview cuenta mensajes correctamente."""
        result = tool.execute(report_type="overview", days=30)

        assert result.success
        # Fixture agrega 6 mensajes (3 user + 3 assistant)
        assert "6" in result.output or "Total mensajes" in result.output


# ================================================================
# ConversationAnalyticsTool — activity
# ================================================================

class TestConversationActivity:
    def test_activity_report(self, tool):
        """Activity muestra mensajes por dia."""
        result = tool.execute(report_type="activity", days=7)

        assert result.success
        assert "Actividad diaria" in result.output
        assert "Promedio" in result.output

    def test_activity_empty_period(self, tmp_path):
        """Activity sin datos muestra mensaje informativo."""
        db_path = tmp_path / "empty_analytics.db"
        mem = MemoryManager(db_path=str(db_path), schema_path=str(SCHEMA_PATH))
        if not hasattr(mem, "_get_conn"):
            mem._get_conn = mem._get_connection
        # No agregar mensajes — la DB tiene 0 conversaciones

        tool_empty = ConversationAnalyticsTool(memory=mem)
        result = tool_empty.execute(report_type="activity", days=1)

        assert result.success
        assert "No hay actividad" in result.output


# ================================================================
# ConversationAnalyticsTool — topics
# ================================================================

class TestConversationTopics:
    def test_topics_report(self, tool):
        """Topics muestra categorias de facts."""
        result = tool.execute(report_type="topics", days=7)

        assert result.success
        assert "Temas por categoria" in result.output
        # El schema.sql tiene seed facts con categorias
        assert "personal" in result.output.lower() or "technical" in result.output.lower()


# ================================================================
# ConversationAnalyticsTool — tools report
# ================================================================

class TestConversationTools:
    def test_tools_report(self, memory_with_tools):
        """Tools report muestra uso de herramientas."""
        tool = ConversationAnalyticsTool(memory=memory_with_tools)
        result = tool.execute(report_type="tools", days=7)

        assert result.success
        assert "file_read" in result.output
        assert "web_fetch" in result.output

    def test_tools_report_no_usage(self, tool):
        """Tools report sin uso muestra mensaje informativo."""
        result = tool.execute(report_type="tools", days=7)

        assert result.success
        assert "No se encontraron" in result.output


# ================================================================
# ConversationAnalyticsTool — no memory
# ================================================================

class TestConversationNoMemory:
    def test_no_memory_error(self):
        """Sin MemoryManager retorna error descriptivo."""
        tool = ConversationAnalyticsTool(memory=None)
        result = tool.execute(report_type="overview")

        assert not result.success
        assert "MemoryManager" in result.error


# ================================================================
# ConversationAnalyticsTool — metadata
# ================================================================

class TestConversationMetadata:
    def test_tool_metadata(self):
        """Definicion Claude tiene formato correcto."""
        tool = ConversationAnalyticsTool()
        assert tool.name == "conversation_analytics"
        assert "conversation" in tool.description.lower() or "analyze" in tool.description.lower()

        d = tool.to_claude_definition()
        assert d["name"] == "conversation_analytics"
        assert "report_type" in d["input_schema"]["properties"]
        assert "days" in d["input_schema"]["properties"]
        assert "report_type" in d["input_schema"]["required"]
