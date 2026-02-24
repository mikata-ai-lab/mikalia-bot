"""
test_telegram_voice.py — Tests para voice messages en Telegram.

Verifica:
- Deteccion de voice messages en updates
- Descarga de archivos de voz
- Transcripcion STT
- Respuesta con TTS
- Envio de audio por Telegram
- Mensajes de texto siguen funcionando
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, mock_open

from mikalia.notifications.telegram_listener import TelegramListener, MikaliaCoreBot


class TestVoiceMessageDetection:

    def test_voice_update_detected(self):
        """Update con voice se procesa correctamente."""
        callback = MagicMock()
        listener = TelegramListener("token", "123", on_message=callback)

        update = {
            "update_id": 1,
            "message": {
                "chat": {"id": 123},
                "voice": {
                    "file_id": "abc123",
                    "duration": 5,
                    "mime_type": "audio/ogg",
                },
            },
        }

        with patch.object(listener, "_download_voice", return_value="/tmp/voice.ogg"):
            listener._process_update(update)

        callback.assert_called_once_with("/tmp/voice.ogg", listener.send, voice=True)

    def test_text_update_still_works(self):
        """Update con texto sigue funcionando normalmente."""
        callback = MagicMock()
        listener = TelegramListener("token", "123", on_message=callback)

        update = {
            "update_id": 2,
            "message": {
                "chat": {"id": 123},
                "text": "hola",
            },
        }

        listener._process_update(update)
        callback.assert_called_once_with("hola", listener.send)

    def test_voice_download_failure(self):
        """Si no se puede descargar el audio, enviar mensaje de error."""
        callback = MagicMock()
        listener = TelegramListener("token", "123", on_message=callback)

        update = {
            "update_id": 3,
            "message": {
                "chat": {"id": 123},
                "voice": {"file_id": "fail123", "duration": 3},
            },
        }

        with patch.object(listener, "_download_voice", return_value=None), \
             patch.object(listener, "send") as mock_send:
            listener._process_update(update)

        callback.assert_not_called()
        mock_send.assert_called_once()

    def test_unauthorized_chat_ignored(self):
        """Voice de chat no autorizado se ignora."""
        callback = MagicMock()
        listener = TelegramListener("token", "123", on_message=callback)

        update = {
            "update_id": 4,
            "message": {
                "chat": {"id": 999},
                "voice": {"file_id": "abc", "duration": 2},
            },
        }

        listener._process_update(update)
        callback.assert_not_called()


class TestVoiceDownload:

    @patch("mikalia.notifications.telegram_listener.requests.get")
    def test_download_voice_success(self, mock_get):
        """Descarga de voice exitosa retorna path local."""
        listener = TelegramListener("test_token", "123")

        # Mock getFile response
        mock_getfile_resp = MagicMock()
        mock_getfile_resp.json.return_value = {
            "ok": True,
            "result": {"file_path": "voice/file_123.ogg"},
        }

        # Mock download response
        mock_download_resp = MagicMock()
        mock_download_resp.content = b"fake ogg data"

        mock_get.side_effect = [mock_getfile_resp, mock_download_resp]

        with patch("mikalia.notifications.telegram_listener.Path.mkdir"), \
             patch("mikalia.notifications.telegram_listener.Path.write_bytes"):
            path = listener._download_voice("file_id_123")

        assert path is not None
        assert "telegram_" in path
        assert path.endswith(".ogg")

    @patch("mikalia.notifications.telegram_listener.requests.get")
    def test_download_voice_api_error(self, mock_get):
        """Error de API retorna None."""
        listener = TelegramListener("test_token", "123")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False}
        mock_get.return_value = mock_resp

        path = listener._download_voice("bad_id")
        assert path is None


class TestVoiceSend:

    @patch("mikalia.notifications.telegram_listener.requests.post")
    def test_send_voice_success(self, mock_post):
        """Envio de audio exitoso."""
        listener = TelegramListener("token", "123")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        with patch("builtins.open", mock_open(read_data=b"mp3data")):
            result = listener.send_voice("/tmp/response.mp3")

        assert result is True
        mock_post.assert_called_once()


class TestCoreVoiceHandling:

    def test_voice_transcription_and_processing(self):
        """Voice message se transcribe y procesa."""
        agent = MagicMock()
        agent._config.mikalia.chat_model = "claude-haiku-4-5-20251001"
        agent.process_message.return_value = "Hola! Todo bien~"
        agent.session_id = "sess1"
        agent.memory.get_last_session.return_value = None

        listener_mock = MagicMock()
        bot = MikaliaCoreBot(agent, listener=listener_mock)
        bot._session_id = "sess1"
        reply = MagicMock()

        with patch.object(bot, "_transcribe_voice", return_value="hola como estas"):
            bot.handle_message("/tmp/audio.ogg", reply, voice=True)

        # Casual text goes through streaming first, or falls back to process_message
        assert (agent.process_message_stream.called or agent.process_message.called)

    def test_voice_transcription_failure(self):
        """Si STT falla, responde con mensaje de error."""
        agent = MagicMock()
        agent.memory.get_last_session.return_value = None

        bot = MikaliaCoreBot(agent)
        bot._session_id = "sess1"
        reply = MagicMock()

        with patch.object(bot, "_transcribe_voice", return_value=None):
            bot.handle_message("/tmp/audio.ogg", reply, voice=True)

        agent.process_message.assert_not_called()
        reply.assert_called_once()
        assert "audio" in reply.call_args[0][0].lower()
