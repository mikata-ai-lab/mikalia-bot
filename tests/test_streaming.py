"""
test_streaming.py — Tests para la funcionalidad de streaming de Mikalia.

Verifica:
- chat_stream() yields chunks correctamente
- chat_stream() retorna APIResponse con tokens al finalizar
- process_message_stream() persiste la respuesta completa en memoria
- MikaliaCoreBot edita mensajes de Telegram durante streaming
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch, call

import pytest

from mikalia.core.agent import MikaliaAgent
from mikalia.core.memory import MemoryManager
from mikalia.generation.client import APIResponse, MikaliaClient
from mikalia.notifications.telegram_listener import (
    MikaliaCoreBot,
    TelegramListener,
    _markdown_to_telegram,
)
from mikalia.tools.registry import ToolRegistry


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


# ================================================================
# Helpers
# ================================================================


def _make_chat_stream_generator(
    chunks: list[str],
    final_response: APIResponse,
) -> Generator[str, None, APIResponse]:
    """
    Construye un generador que simula chat_stream():
    yield fragmentos y retorna un APIResponse al final.
    """
    for chunk in chunks:
        yield chunk
    return final_response


def _make_api_response(
    content: str = "Hola Mikata-kun!",
    input_tokens: int = 80,
    output_tokens: int = 40,
) -> APIResponse:
    """Helper para crear APIResponse de test."""
    return APIResponse(
        content=content,
        model="claude-test",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        stop_reason="end_turn",
    )


@pytest.fixture
def memory(tmp_path):
    db_path = tmp_path / "test_stream.db"
    return MemoryManager(str(db_path), str(SCHEMA_PATH))


@pytest.fixture
def mock_client():
    """MikaliaClient mockeado."""
    return MagicMock(spec=MikaliaClient)


@pytest.fixture
def mock_config():
    """Config minima para el agent."""
    config = MagicMock()
    config.anthropic_api_key = "test-key"
    config.mikalia.model = "claude-test"
    config.mikalia.chat_model = "claude-haiku-test"
    config.mikalia.generation_temperature = 0.7
    config.mikalia.max_tokens = 1024
    return config


# ================================================================
# test_chat_stream_yields_chunks
# ================================================================


class TestChatStreamYieldsChunks:
    """Verifica que chat_stream() entrega fragmentos de texto."""

    def test_yields_all_chunks(self):
        """El generador debe entregar cada fragmento del stream."""
        chunks = ["Hola ", "Mikata", "-kun", "! Como ", "estas?"]
        final = _make_api_response("Hola Mikata-kun! Como estas?")

        # Simular el stream context manager del SDK
        mock_sdk_client = MagicMock()
        mock_stream_cm = MagicMock()
        mock_stream = MagicMock()
        mock_stream.text_stream = iter(chunks)
        mock_final_msg = MagicMock()
        mock_final_msg.model = "claude-test"
        mock_final_msg.usage.input_tokens = 80
        mock_final_msg.usage.output_tokens = 40
        mock_final_msg.stop_reason = "end_turn"
        mock_stream.get_final_message.return_value = mock_final_msg

        mock_stream_cm.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_cm.__exit__ = MagicMock(return_value=False)
        mock_sdk_client.messages.stream.return_value = mock_stream_cm

        client = MikaliaClient.__new__(MikaliaClient)
        client._client = mock_sdk_client
        client._model = "claude-test"
        client._system_prompt = "Eres Mikalia."
        client._max_retries = 1

        gen = client.chat_stream(
            messages=[{"role": "user", "content": "Hola"}],
        )

        received = []
        try:
            while True:
                received.append(next(gen))
        except StopIteration:
            pass

        assert received == chunks

    def test_multiple_chunks_arrive_in_order(self):
        """Los fragmentos llegan en el orden correcto."""
        ordered = ["1-", "2-", "3-", "4-", "5"]
        mock_sdk_client = MagicMock()
        mock_stream_cm = MagicMock()
        mock_stream = MagicMock()
        mock_stream.text_stream = iter(ordered)
        mock_final = MagicMock()
        mock_final.model = "claude-test"
        mock_final.usage.input_tokens = 10
        mock_final.usage.output_tokens = 5
        mock_final.stop_reason = "end_turn"
        mock_stream.get_final_message.return_value = mock_final
        mock_stream_cm.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_cm.__exit__ = MagicMock(return_value=False)
        mock_sdk_client.messages.stream.return_value = mock_stream_cm

        client = MikaliaClient.__new__(MikaliaClient)
        client._client = mock_sdk_client
        client._model = "claude-test"
        client._system_prompt = ""
        client._max_retries = 1

        gen = client.chat_stream(
            messages=[{"role": "user", "content": "count"}],
        )

        received = list(_exhaust_gen(gen))
        assert "".join(received) == "1-2-3-4-5"


# ================================================================
# test_stream_returns_api_response
# ================================================================


class TestStreamReturnsAPIResponse:
    """Verifica que el generador retorna APIResponse con uso de tokens."""

    def test_final_response_has_token_count(self):
        """La APIResponse final tiene input_tokens y output_tokens."""
        mock_sdk_client = MagicMock()
        mock_stream_cm = MagicMock()
        mock_stream = MagicMock()
        mock_stream.text_stream = iter(["Hola!"])
        mock_final = MagicMock()
        mock_final.model = "claude-test"
        mock_final.usage.input_tokens = 150
        mock_final.usage.output_tokens = 75
        mock_final.stop_reason = "end_turn"
        mock_stream.get_final_message.return_value = mock_final
        mock_stream_cm.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream_cm.__exit__ = MagicMock(return_value=False)
        mock_sdk_client.messages.stream.return_value = mock_stream_cm

        client = MikaliaClient.__new__(MikaliaClient)
        client._client = mock_sdk_client
        client._model = "claude-test"
        client._system_prompt = ""
        client._max_retries = 1

        gen = client.chat_stream(
            messages=[{"role": "user", "content": "Hola"}],
        )

        api_response = _exhaust_gen_return(gen)

        assert isinstance(api_response, APIResponse)
        assert api_response.input_tokens == 150
        assert api_response.output_tokens == 75
        assert api_response.content == "Hola!"
        assert api_response.model == "claude-test"
        assert api_response.stop_reason == "end_turn"


# ================================================================
# test_process_message_stream_persists
# ================================================================


class TestProcessMessageStreamPersists:
    """Verifica que la respuesta completa se persiste en memoria."""

    def test_full_response_saved_to_memory(
        self, memory, mock_client, mock_config
    ):
        """El texto completo se guarda en memoria despues del stream."""
        chunks = ["Hola ", "Mikata-", "kun~"]
        final = _make_api_response(
            "Hola Mikata-kun~", input_tokens=100, output_tokens=30
        )

        mock_client.chat_stream.return_value = _make_chat_stream_generator(
            chunks, final
        )

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        # Consumir todo el generador
        collected = []
        for chunk in agent.process_message_stream(
            "Hola", channel="cli"
        ):
            collected.append(chunk)

        # Verificar chunks
        assert collected == chunks

        # Verificar persistencia en memoria
        session_id = agent.session_id
        messages = memory.get_session_messages(session_id)
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["content"] == "Hola Mikata-kun~"

    def test_user_message_also_persisted(
        self, memory, mock_client, mock_config
    ):
        """El mensaje del usuario tambien se guarda en memoria."""
        chunks = ["OK"]
        final = _make_api_response("OK", input_tokens=50, output_tokens=10)
        mock_client.chat_stream.return_value = _make_chat_stream_generator(
            chunks, final
        )

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        # Consumir generador
        list(agent.process_message_stream("Pregunta", channel="cli"))

        session_id = agent.session_id
        messages = memory.get_session_messages(session_id)
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert any(m["content"] == "Pregunta" for m in user_msgs)


# ================================================================
# test_telegram_stream_edits_message
# ================================================================


class TestTelegramStreamEditsMessage:
    """Verifica que MikaliaCoreBot edita mensajes durante streaming."""

    def test_edit_message_text_called(self, memory, mock_config):
        """editMessageText se llama durante streaming de Telegram."""
        # Setup agent con streaming mock
        mock_client = MagicMock(spec=MikaliaClient)

        # Simular chunks grandes para que streaming envie mensaje
        chunks = ["Hola " * 5, "Mikata-kun, ", "como estas? " * 10]
        final = _make_api_response(
            "".join(chunks), input_tokens=80, output_tokens=40
        )
        mock_client.chat_stream.return_value = _make_chat_stream_generator(
            chunks, final
        )
        # Tambien necesitamos chat_with_tools por si acaso
        mock_client.chat_with_tools.return_value = _make_api_response()

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        # Setup listener mock
        listener = MagicMock(spec=TelegramListener)
        listener.send_and_edit.return_value = 42  # message_id
        listener.edit_message.return_value = True
        listener.send_typing.return_value = None

        bot = MikaliaCoreBot(agent=agent, listener=listener)

        reply = MagicMock()

        # Parchear time.time para controlar intervalos
        times = iter([
            0.0,   # primera vez: chunk 1, no message_id yet
            0.0,   # send_and_edit
            2.0,   # chunk 2: 2s > 1.5s interval -> edit
            4.0,   # chunk 3: 4s > 1.5s interval -> edit
            6.0,   # final edit
        ])

        with patch(
            "mikalia.notifications.telegram_listener.time.time",
            side_effect=lambda: next(times, 10.0),
        ):
            bot.handle_message("hola que tal", reply)

        # Verificar que send_and_edit fue llamado (mensaje inicial)
        listener.send_and_edit.assert_called()

        # Verificar que edit_message fue llamado (actualizaciones)
        assert listener.edit_message.call_count >= 1

    def test_fallback_on_stream_failure(self, memory, mock_config):
        """Si streaming falla, se usa process_message como fallback."""
        mock_client = MagicMock(spec=MikaliaClient)
        mock_client.chat_stream.side_effect = Exception("Stream error")
        mock_client.chat_with_tools.return_value = _make_api_response(
            "Respuesta normal"
        )

        agent = MikaliaAgent(
            config=mock_config,
            memory=memory,
            client=mock_client,
            tool_registry=ToolRegistry(),
        )

        listener = MagicMock(spec=TelegramListener)
        listener.send_typing.return_value = None
        bot = MikaliaCoreBot(agent=agent, listener=listener)

        reply = MagicMock()
        bot.handle_message("hola", reply)

        # reply debio ser llamado con la respuesta normal
        assert reply.called


# ================================================================
# Utilidades para agotar generadores con return value
# ================================================================


def _exhaust_gen(gen: Generator) -> list[str]:
    """Consume un generador y retorna los valores yielded."""
    results = []
    try:
        while True:
            results.append(next(gen))
    except StopIteration:
        pass
    return results


def _exhaust_gen_return(gen: Generator) -> APIResponse | None:
    """Consume un generador y retorna su valor de return."""
    try:
        while True:
            next(gen)
    except StopIteration as stop:
        return stop.value
    return None
