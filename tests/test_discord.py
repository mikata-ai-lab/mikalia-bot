"""
test_discord.py — Tests para DiscordListener de Mikalia.

Verifica:
- Callback de mensajes del canal autorizado
- Ignora mensajes propios del bot
- Ignora mensajes de canales no autorizados
- Envio de mensajes y split por limite de 2000 chars
- Indicador de typing

Usa mocks completos de discord.py para evitar dependencias en CI.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock, patch, AsyncMock


# ================================================================
# Mock completo de discord antes de importar el modulo
# ================================================================

_mock_discord = MagicMock()
_mock_discord.Intents.default.return_value = MagicMock(message_content=False)
_mock_discord.Client = MagicMock


def _make_mock_client(**kwargs):
    """Crea un mock de discord.Client con event decorator funcional."""
    client = MagicMock()
    client._events = {}

    def event(func):
        client._events[func.__name__] = func
        return func

    client.event = event
    return client


_mock_discord.Client = _make_mock_client
sys.modules["discord"] = _mock_discord

from mikalia.notifications.discord_listener import DiscordListener, MAX_MESSAGE_LENGTH  # noqa: E402


# ================================================================
# Helpers
# ================================================================

def _make_listener(on_message=None):
    """Crea un DiscordListener con mocks inyectados."""
    listener = DiscordListener(
        bot_token="fake-token",
        channel_id=123456,
        on_message=on_message,
    )
    return listener


def _make_message(content, author_name="Mikata", channel_id=123456, is_bot_user=False):
    """Crea un mock de discord.Message."""
    msg = MagicMock()
    msg.content = content
    msg.author = MagicMock()
    msg.author.__str__ = lambda self: author_name
    msg.channel = MagicMock()
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()

    # Para la comparacion message.author == self._bot.user
    if is_bot_user:
        msg.author.__eq__ = lambda self, other: True
    else:
        msg.author.__eq__ = lambda self, other: False

    return msg


def _run_async(coro):
    """Ejecuta una coroutine en un loop temporal."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ================================================================
# Tests
# ================================================================

class TestDiscordListener:

    def test_message_callback(self):
        """Mensaje del canal autorizado dispara el callback."""
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = _make_listener(on_message=on_msg)
        on_message_handler = listener._bot._events["on_message"]

        msg = _make_message("Hola Mikalia!", channel_id=123456)
        _run_async(on_message_handler(msg))

        assert received == ["Hola Mikalia!"]

    def test_ignore_own_messages(self):
        """El bot ignora sus propios mensajes."""
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = _make_listener(on_message=on_msg)
        on_message_handler = listener._bot._events["on_message"]

        msg = _make_message("Echo!", is_bot_user=True)
        _run_async(on_message_handler(msg))

        assert received == []

    def test_channel_filter(self):
        """Mensajes de canales no autorizados se ignoran."""
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = _make_listener(on_message=on_msg)
        on_message_handler = listener._bot._events["on_message"]

        msg = _make_message("Hacker!", channel_id=999999)
        _run_async(on_message_handler(msg))

        assert received == []

    def test_send_message(self):
        """send() delega al channel.send() via _async_send."""
        listener = _make_listener()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        listener._channel = mock_channel

        _run_async(listener._async_send("Hola!"))

        mock_channel.send.assert_awaited_once_with("Hola!")

    def test_long_message_split(self):
        """Mensajes mayores a 2000 chars se dividen en chunks."""
        listener = _make_listener()
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        listener._channel = mock_channel

        # Texto de 4500 chars -> 3 chunks (2000 + 2000 + 500)
        long_text = "A" * 4500
        _run_async(listener._async_send(long_text))

        assert mock_channel.send.await_count == 3
        calls = [c.args[0] for c in mock_channel.send.await_args_list]
        assert len(calls[0]) == 2000
        assert len(calls[1]) == 2000
        assert len(calls[2]) == 500
        assert "".join(calls) == long_text

    def test_send_typing(self):
        """send_typing() invoca channel.typing() via el event loop."""
        listener = _make_listener()
        mock_channel = MagicMock()
        mock_channel.typing = AsyncMock()
        listener._channel = mock_channel

        # Simular loop del bot corriendo en otro thread
        loop = asyncio.new_event_loop()
        listener._bot.loop = loop

        import threading
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()

        try:
            listener.send_typing()
            mock_channel.typing.assert_awaited_once()
        finally:
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=2)
            loop.close()

    def test_empty_message_ignored(self):
        """Mensajes vacios se ignoran."""
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = _make_listener(on_message=on_msg)
        on_message_handler = listener._bot._events["on_message"]

        msg = _make_message("   ", channel_id=123456)
        _run_async(on_message_handler(msg))

        assert received == []

    def test_send_no_channel_logs_error(self):
        """send() sin canal destino loguea error y no crashea."""
        listener = _make_listener()
        listener._channel = None

        # No debe lanzar excepcion
        _run_async(listener._async_send("Hola!"))

    def test_on_ready_sets_channel(self):
        """on_ready() obtiene el canal por ID."""
        listener = _make_listener()
        mock_channel = MagicMock()
        listener._bot.get_channel = MagicMock(return_value=mock_channel)

        on_ready_handler = listener._bot._events["on_ready"]
        _run_async(on_ready_handler())

        listener._bot.get_channel.assert_called_once_with(123456)
        assert listener._channel is mock_channel

    def test_reply_fn_provided_to_callback(self):
        """El callback recibe un reply_fn callable."""
        reply_fns = []

        def on_msg(text, reply_fn):
            reply_fns.append(reply_fn)

        listener = _make_listener(on_message=on_msg)
        on_message_handler = listener._bot._events["on_message"]

        msg = _make_message("Test", channel_id=123456)
        _run_async(on_message_handler(msg))

        assert len(reply_fns) == 1
        assert callable(reply_fns[0])
