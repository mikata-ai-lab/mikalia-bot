"""
test_web_chat.py — Tests para el web chat de Mikalia.

Verifica:
- GET /chat sirve pagina HTML
- POST /api/chat retorna respuesta sincrona
- POST /api/chat/stream retorna eventos SSE
- GET /api/chat/history retorna historial
- Smart routing: casual → streaming, tools → Sonnet
- Manejo de sesiones
- Manejo de errores
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from mikalia.api import create_app
from mikalia.core.memory import MemoryManager
from mikalia.web.routes import _classify_message


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    db_path = tmp_path / "test_web.db"
    return MemoryManager(str(db_path), str(SCHEMA_PATH))


@dataclass
class _FakeMikaliaConfig:
    chat_model: str = "claude-haiku-4-5-20251001"


@dataclass
class _FakeConfig:
    mikalia: _FakeMikaliaConfig = None

    def __post_init__(self):
        if self.mikalia is None:
            self.mikalia = _FakeMikaliaConfig()


@pytest.fixture
def mock_agent(memory):
    """MikaliaAgent mock con memoria real."""
    agent = MagicMock()
    agent.memory = memory
    agent.process_message.return_value = "Hola! Soy Mikalia~"
    agent.session_id = "test-session"
    agent._config = _FakeConfig()

    def fake_stream(message, channel="web", session_id=None, model_override=None):
        yield "Hola"
        yield "! Soy "
        yield "Mikalia~"

    agent.process_message_stream.side_effect = fake_stream
    return agent


@pytest.fixture
def client(mock_agent, memory):
    app = create_app(memory=memory, agent=mock_agent)
    return TestClient(app)


# ================================================================
# Chat page
# ================================================================

class TestChatPage:

    def test_chat_page_returns_html(self, client):
        """GET /chat retorna HTML."""
        resp = client.get("/chat")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_chat_page_has_mikalia_branding(self, client):
        """HTML contiene branding de Mikalia."""
        resp = client.get("/chat")
        assert "Mikalia" in resp.text

    def test_chat_page_has_static_links(self, client):
        """HTML tiene links a CSS y JS."""
        resp = client.get("/chat")
        assert "/static/chat.css" in resp.text
        assert "/static/chat.js" in resp.text


# ================================================================
# Sync chat
# ================================================================

class TestSyncChat:

    def test_chat_returns_response(self, client, mock_agent):
        """POST /api/chat retorna respuesta."""
        resp = client.post("/api/chat", json={"message": "hola"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Hola! Soy Mikalia~"

    def test_chat_creates_session(self, client):
        """POST /api/chat sin session_id crea una nueva."""
        resp = client.post("/api/chat", json={"message": "hola"})
        data = resp.json()
        assert data["session_id"] is not None
        assert len(data["session_id"]) > 0

    def test_chat_reuses_session(self, client, mock_agent):
        """POST /api/chat con session_id existente lo reutiliza."""
        # Primera llamada — crea sesion
        resp1 = client.post("/api/chat", json={"message": "hola"})
        session_id = resp1.json()["session_id"]

        # Segunda llamada — reutiliza
        resp2 = client.post("/api/chat", json={
            "message": "que tal",
            "session_id": session_id,
        })
        assert resp2.json()["session_id"] == session_id

    def test_chat_no_agent_returns_error(self, memory):
        """POST /api/chat sin agent retorna error."""
        app = create_app(memory=memory, agent=None)
        no_agent_client = TestClient(app)
        resp = no_agent_client.post("/api/chat", json={"message": "hola"})
        data = resp.json()
        assert "error" in data


# ================================================================
# SSE streaming
# ================================================================

class TestChatStream:

    def test_stream_returns_sse_content_type(self, client):
        """POST /api/chat/stream retorna text/event-stream."""
        resp = client.post("/api/chat/stream", json={"message": "hola"})
        assert "text/event-stream" in resp.headers["content-type"]

    def test_stream_sends_session_first(self, client):
        """Primer evento SSE es session con session_id."""
        resp = client.post("/api/chat/stream", json={"message": "hola"})
        lines = resp.text.strip().split("\n\n")
        first_event = json.loads(lines[0].replace("data: ", ""))
        assert first_event["type"] == "session"
        assert first_event["session_id"] is not None

    def test_stream_sends_chunks(self, client):
        """Eventos SSE contienen chunks de texto."""
        resp = client.post("/api/chat/stream", json={"message": "hola"})
        lines = resp.text.strip().split("\n\n")
        chunks = [
            json.loads(line.replace("data: ", ""))
            for line in lines
            if line.startswith("data: ")
        ]
        chunk_events = [c for c in chunks if c["type"] == "chunk"]
        assert len(chunk_events) == 3
        assert chunk_events[0]["text"] == "Hola"
        assert chunk_events[1]["text"] == "! Soy "
        assert chunk_events[2]["text"] == "Mikalia~"

    def test_stream_sends_done(self, client):
        """Ultimo evento SSE es done."""
        resp = client.post("/api/chat/stream", json={"message": "hola"})
        lines = resp.text.strip().split("\n\n")
        last_event = json.loads(lines[-1].replace("data: ", ""))
        assert last_event["type"] == "done"

    def test_stream_no_agent_returns_error(self, memory):
        """SSE sin agent envia evento de error."""
        app = create_app(memory=memory, agent=None)
        no_agent_client = TestClient(app)
        resp = no_agent_client.post(
            "/api/chat/stream", json={"message": "hola"}
        )
        first_event = json.loads(
            resp.text.strip().split("\n\n")[0].replace("data: ", "")
        )
        assert first_event["type"] == "error"


# ================================================================
# Chat history
# ================================================================

class TestChatHistory:

    def test_history_returns_messages(self, client, memory):
        """GET /api/chat/history retorna mensajes de la sesion."""
        session_id = memory.create_session("web")
        memory.add_message(session_id, "web", "user", "hola")
        memory.add_message(session_id, "web", "assistant", "hey!")

        resp = client.get(f"/api/chat/history?session_id={session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    def test_history_empty_session(self, client, memory):
        """Sesion sin mensajes retorna lista vacia."""
        session_id = memory.create_session("web")
        resp = client.get(f"/api/chat/history?session_id={session_id}")
        data = resp.json()
        assert data["messages"] == []

    def test_delete_history(self, client, memory):
        """DELETE /api/chat/history borra mensajes de la sesion."""
        session_id = memory.create_session("web")
        memory.add_message(session_id, "web", "user", "hola")
        memory.add_message(session_id, "web", "assistant", "hey!")

        resp = client.delete(f"/api/chat/history?session_id={session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] == 2
        assert data["session_id"] == session_id

        # Verify history is empty now
        resp2 = client.get(f"/api/chat/history?session_id={session_id}")
        assert resp2.json()["messages"] == []

    def test_delete_history_empty_session(self, client, memory):
        """DELETE en sesion vacia retorna deleted=0."""
        session_id = memory.create_session("web")
        resp = client.delete(f"/api/chat/history?session_id={session_id}")
        assert resp.json()["deleted"] == 0

    def test_delete_history_no_agent(self, memory):
        """DELETE sin agent retorna deleted=0."""
        app = create_app(memory=memory, agent=None)
        no_agent_client = TestClient(app)
        resp = no_agent_client.delete("/api/chat/history?session_id=fake")
        assert resp.json()["deleted"] == 0

    def test_chat_page_has_clear_button(self, client):
        """HTML tiene boton de borrar historial."""
        resp = client.get("/chat")
        assert "clear-btn" in resp.text


# ================================================================
# Smart routing
# ================================================================

class TestSmartRouting:

    def test_classify_greeting_as_casual(self):
        """Saludo se clasifica como casual."""
        assert _classify_message("hola que onda") == "casual"

    def test_classify_short_question_as_casual(self):
        """Pregunta corta es casual."""
        assert _classify_message("como estas?") == "casual"

    def test_classify_tool_keyword_as_tools(self):
        """Keyword de tool se clasifica como tools."""
        assert _classify_message("hazme un post sobre IA") == "tools"

    def test_classify_code_keyword_as_tools(self):
        """Keyword de codigo se clasifica como tools."""
        assert _classify_message("analiza este repo") == "tools"

    def test_classify_long_message_as_tools(self):
        """Mensaje largo (>150 chars) se clasifica como tools."""
        assert _classify_message("a" * 151) == "tools"

    def test_casual_uses_streaming(self, client, mock_agent):
        """Mensaje casual usa process_message_stream (Haiku)."""
        client.post("/api/chat/stream", json={"message": "hola"})
        mock_agent.process_message_stream.assert_called_once()
        call_kwargs = mock_agent.process_message_stream.call_args
        assert call_kwargs.kwargs.get("model_override") == "claude-haiku-4-5-20251001"

    def test_tools_uses_process_message(self, client, mock_agent):
        """Mensaje con tool keyword usa process_message (Sonnet)."""
        client.post("/api/chat/stream", json={"message": "hazme un post sobre AI"})
        mock_agent.process_message.assert_called_once()
        call_kwargs = mock_agent.process_message.call_args
        assert call_kwargs.kwargs.get("model_override") is None

    def test_stream_fallback_on_error(self, client, mock_agent):
        """Si streaming falla, cae a process_message sync."""
        mock_agent.process_message_stream.side_effect = Exception("stream error")
        resp = client.post("/api/chat/stream", json={"message": "hola"})
        events = [
            json.loads(line.replace("data: ", ""))
            for line in resp.text.strip().split("\n\n")
            if line.startswith("data: ")
        ]
        chunk_events = [e for e in events if e["type"] == "chunk"]
        assert len(chunk_events) == 1
        assert chunk_events[0]["text"] == "Hola! Soy Mikalia~"
