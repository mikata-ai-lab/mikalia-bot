"""
test_core_agent.py — Tests para el agent loop de Mikalia Core.

Verifica el flujo completo con LLM mockeado:
- Mensajes simples (sin tool calls)
- Persistencia en memoria
- Manejo de tool calls
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from mikalia.core.agent import MikaliaAgent
from mikalia.core.memory import MemoryManager
from mikalia.generation.client import APIResponse
from mikalia.tools.registry import ToolRegistry


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    db_path = tmp_path / "test_agent.db"
    return MemoryManager(str(db_path), str(SCHEMA_PATH))


@pytest.fixture
def mock_client():
    """MikaliaClient mockeado."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_config():
    """Config minima para el agent."""
    config = MagicMock()
    config.anthropic_api_key = "test-key"
    config.mikalia.model = "claude-test"
    config.mikalia.generation_temperature = 0.7
    config.mikalia.max_tokens = 1024
    return config


def make_response(
    content: str = "Hola Mikata-kun!",
    stop_reason: str = "end_turn",
    tool_calls: list | None = None,
    raw_content: list | None = None,
) -> APIResponse:
    """Helper para crear APIResponse de test."""
    return APIResponse(
        content=content,
        model="claude-test",
        input_tokens=100,
        output_tokens=50,
        stop_reason=stop_reason,
        tool_calls=tool_calls or [],
        raw_content=raw_content or [{"type": "text", "text": content}],
    )


# ================================================================
# Mensajes simples
# ================================================================

class TestSimpleMessage:
    def test_returns_llm_response(self, memory, mock_client, mock_config):
        """El agent retorna la respuesta del LLM."""
        mock_client.chat_with_tools.return_value = make_response(
            "Hola! Soy Mikalia~"
        )

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        response = agent.process_message("Hola", channel="cli")
        assert response == "Hola! Soy Mikalia~"

    def test_persists_user_message(self, memory, mock_client, mock_config):
        """El mensaje del usuario se guarda en memoria."""
        mock_client.chat_with_tools.return_value = make_response()

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        agent.process_message("Test msg", channel="cli")

        # Verificar que el mensaje se guardo
        session_id = agent.session_id
        messages = memory.get_session_messages(session_id)
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) >= 1
        assert any(m["content"] == "Test msg" for m in user_msgs)

    def test_persists_assistant_response(self, memory, mock_client, mock_config):
        """La respuesta del asistente se guarda en memoria."""
        mock_client.chat_with_tools.return_value = make_response(
            "Respuesta guardada"
        )

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        agent.process_message("Pregunta", channel="cli")

        session_id = agent.session_id
        messages = memory.get_session_messages(session_id)
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) >= 1
        assert assistant_msgs[0]["content"] == "Respuesta guardada"

    def test_creates_session(self, memory, mock_client, mock_config):
        """El agent crea una sesion automaticamente."""
        mock_client.chat_with_tools.return_value = make_response()

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        agent.process_message("Hola", channel="cli")
        assert agent.session_id is not None

        session = memory.get_session(agent.session_id)
        assert session is not None
        assert session["channel"] == "cli"


# ================================================================
# Tool calls
# ================================================================

class TestToolCalls:
    def test_executes_tool_and_continues(
        self, memory, mock_client, mock_config, tmp_path
    ):
        """El agent ejecuta tools y continua hasta respuesta final."""
        # Crear archivo para que file_read lo lea
        test_file = tmp_path / "readme.txt"
        test_file.write_text("Mikalia Core", encoding="utf-8")

        # Primera respuesta: tool call
        tool_response = make_response(
            content="",
            stop_reason="tool_use",
            tool_calls=[{
                "id": "tool_1",
                "name": "file_read",
                "input": {"path": str(test_file)},
            }],
            raw_content=[{
                "type": "tool_use",
                "id": "tool_1",
                "name": "file_read",
                "input": {"path": str(test_file)},
            }],
        )

        # Segunda respuesta: texto final
        final_response = make_response("Lei el archivo. Dice: Mikalia Core")

        mock_client.chat_with_tools.side_effect = [tool_response, final_response]

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry.with_defaults(),
        )

        response = agent.process_message("Lee el readme", channel="cli")
        assert "Mikalia Core" in response

        # Verificar que se llamo 2 veces (tool round + final)
        assert mock_client.chat_with_tools.call_count == 2

    def test_max_rounds_safety(self, memory, mock_client, mock_config):
        """El agent no hace mas de MAX_TOOL_ROUNDS rondas."""
        # Respuesta que siempre pide tool calls (loop infinito)
        infinite_tool = make_response(
            content="",
            stop_reason="tool_use",
            tool_calls=[{
                "id": "tool_x",
                "name": "nonexistent_tool",
                "input": {},
            }],
            raw_content=[{
                "type": "tool_use",
                "id": "tool_x",
                "name": "nonexistent_tool",
                "input": {},
            }],
        )

        mock_client.chat_with_tools.return_value = infinite_tool

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )
        agent.MAX_TOOL_ROUNDS = 3  # Reducir para test rapido

        agent.process_message("Loop infinito", channel="cli")

        # 1 initial + 3 tool rounds = 4 calls
        assert mock_client.chat_with_tools.call_count == 4
