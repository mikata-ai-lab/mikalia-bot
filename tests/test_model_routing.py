"""
test_model_routing.py — Tests para smart model routing.

Verifica:
- Clasificador de mensajes (casual vs tools)
- Routing correcto (Haiku para casual, Sonnet para tools)
- model_override se pasa al agent
- skip_tools se respeta
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from mikalia.notifications.telegram_listener import MikaliaCoreBot, _TOOL_KEYWORDS


# ================================================================
# Message Classifier
# ================================================================

class TestMessageClassifier:

    def test_greeting_is_casual(self):
        """Saludo simple se clasifica como casual."""
        assert MikaliaCoreBot._classify_message("hola que onda") == "casual"

    def test_short_question_is_casual(self):
        """Pregunta corta se clasifica como casual."""
        assert MikaliaCoreBot._classify_message("como estas?") == "casual"

    def test_emoji_is_casual(self):
        """Emojis y reacciones son casual."""
        assert MikaliaCoreBot._classify_message("jaja xd") == "casual"

    def test_tool_keyword_is_tools(self):
        """Mensaje con keyword de tool se clasifica como tools."""
        assert MikaliaCoreBot._classify_message("hazme un post sobre IA") == "tools"

    def test_action_keyword_is_tools(self):
        """Mensaje con keyword de accion se clasifica como tools."""
        assert MikaliaCoreBot._classify_message("analiza este repo") == "tools"

    def test_code_keyword_is_tools(self):
        """Mensaje sobre codigo se clasifica como tools."""
        assert MikaliaCoreBot._classify_message("revisa el code del PR") == "tools"

    def test_long_message_is_tools(self):
        """Mensaje largo (>150 chars) se clasifica como tools."""
        long_msg = "a" * 151
        assert MikaliaCoreBot._classify_message(long_msg) == "tools"

    def test_short_without_keywords_is_casual(self):
        """Mensaje corto sin keywords es casual."""
        assert MikaliaCoreBot._classify_message("que piensas de eso?") == "casual"

    def test_case_insensitive(self):
        """Keywords se detectan case-insensitive."""
        assert MikaliaCoreBot._classify_message("HAZME UN POST") == "tools"

    def test_tool_keywords_set_not_empty(self):
        """El set de keywords no esta vacio."""
        assert len(_TOOL_KEYWORDS) > 20


# ================================================================
# Model Routing Integration
# ================================================================

class TestModelRouting:

    def _make_bot(self):
        """Crea un MikaliaCoreBot con mocks."""
        agent = MagicMock()
        agent._config.mikalia.chat_model = "claude-haiku-4-5-20251001"
        agent.process_message.return_value = "respuesta de test"
        agent.session_id = "test-session"
        agent.memory.get_last_session.return_value = None
        listener = MagicMock()
        bot = MikaliaCoreBot(agent, listener=listener)
        bot._session_id = "test-session"
        return bot, agent

    def test_casual_tries_stream_first(self):
        """Mensaje casual intenta streaming primero (process_message_stream)."""
        bot, agent = self._make_bot()

        bot.handle_message("hola que tal", MagicMock())

        # Casual messages try streaming first via process_message_stream
        agent.process_message_stream.assert_called_once_with(
            message="hola que tal",
            channel="telegram",
            session_id="test-session",
            model_override="claude-haiku-4-5-20251001",
        )

    def test_casual_falls_back_to_process_message(self):
        """Si streaming falla, casual cae a process_message."""
        bot, agent = self._make_bot()
        agent.process_message_stream.side_effect = Exception("stream error")

        bot.handle_message("hola que tal", MagicMock())

        agent.process_message.assert_called_once_with(
            message="hola que tal",
            channel="telegram",
            session_id="test-session",
            model_override="claude-haiku-4-5-20251001",
            skip_tools=True,
        )

    def test_tools_uses_default_model(self):
        """Mensaje con tool keyword llama a process_message sin model_override."""
        bot, agent = self._make_bot()

        bot.handle_message("hazme un post sobre AI", MagicMock())

        agent.process_message.assert_called_once_with(
            message="hazme un post sobre AI",
            channel="telegram",
            session_id="test-session",
        )

    def test_slash_commands_skip_routing(self):
        """Comandos /start, /help, etc. no pasan por el clasificador."""
        bot, agent = self._make_bot()
        reply = MagicMock()

        bot.handle_message("/start", reply)

        # No debe llamar a process_message
        agent.process_message.assert_not_called()
        # Debe responder con el saludo
        reply.assert_called_once()
