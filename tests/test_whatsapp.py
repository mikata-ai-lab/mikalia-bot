"""
test_whatsapp.py — Tests para integracion WhatsApp de Mikalia.

Verifica:
- WhatsAppChannel: envio de notificaciones
- WhatsAppListener: verificacion de webhook, procesamiento de mensajes
- Endpoints de FastAPI para WhatsApp
- Seguridad: solo numeros autorizados
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from mikalia.notifications.whatsapp import (
    WhatsAppChannel,
    WhatsAppListener,
    API_BASE,
)
from mikalia.notifications.notifier import Event


# ================================================================
# WhatsAppChannel (notificaciones one-way)
# ================================================================

class TestWhatsAppChannel:
    def test_is_configured_true(self):
        ch = WhatsAppChannel("phone123", "token_abc", "521234567890")
        assert ch.is_configured()

    def test_is_configured_false_no_phone(self):
        ch = WhatsAppChannel("", "token_abc", "521234567890")
        assert not ch.is_configured()

    def test_is_configured_false_no_token(self):
        ch = WhatsAppChannel("phone123", "", "521234567890")
        assert not ch.is_configured()

    def test_is_configured_false_no_recipient(self):
        ch = WhatsAppChannel("phone123", "token_abc", "")
        assert not ch.is_configured()

    @patch("mikalia.notifications.whatsapp.requests.post")
    def test_send_message_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"messages": [{"id": "wamid.123"}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()

        ch = WhatsAppChannel("phone123", "token_abc", "521234567890")
        result = ch._send_message("Hola!")

        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["messaging_product"] == "whatsapp"
        assert payload["to"] == "521234567890"
        assert payload["text"]["body"] == "Hola!"

    @patch("mikalia.notifications.whatsapp.requests.post")
    def test_send_message_timeout(self, mock_post):
        import requests as req
        mock_post.side_effect = req.Timeout("timeout")

        ch = WhatsAppChannel("phone123", "token_abc", "521234567890")
        result = ch._send_message("Hola!")

        assert result is False

    @patch("mikalia.notifications.whatsapp.requests.post")
    def test_send_event(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"messages": [{"id": "wamid.123"}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()

        ch = WhatsAppChannel("phone123", "token_abc", "521234567890")
        result = ch.send(Event.POST_PUBLISHED, {"title": "Mi Post", "url": "http://x.com"})

        assert result is True

    def test_send_unknown_event(self):
        """Evento sin template retorna False sin crash."""
        ch = WhatsAppChannel("phone123", "token_abc", "521234567890")
        # Crear un evento que no tiene template (hackeamos con un valor custom)
        # En realidad todos los Event tienen template, asi que verificamos que
        # el canal maneja datos faltantes
        with patch.object(ch, "_templates", {}):
            result = ch.send(Event.POST_PUBLISHED, {})
            assert result is False


# ================================================================
# WhatsAppListener (webhook bidireccional)
# ================================================================

class TestWhatsAppListener:
    def _make_listener(self, **kwargs):
        return WhatsAppListener(
            phone_number_id="phone123",
            access_token="token_abc",
            verify_token="mi_secreto",
            allowed_numbers=["521234567890"],
            **kwargs,
        )

    def test_verify_token_property(self):
        listener = self._make_listener()
        assert listener.verify_token == "mi_secreto"

    def test_webhook_verify_success(self):
        listener = self._make_listener()
        result = listener.handle_webhook_verify(
            mode="subscribe",
            token="mi_secreto",
            challenge="challenge_abc",
        )
        assert result == "challenge_abc"

    def test_webhook_verify_wrong_token(self):
        listener = self._make_listener()
        result = listener.handle_webhook_verify(
            mode="subscribe",
            token="wrong_token",
            challenge="challenge_abc",
        )
        assert result is None

    def test_webhook_verify_wrong_mode(self):
        listener = self._make_listener()
        result = listener.handle_webhook_verify(
            mode="unsubscribe",
            token="mi_secreto",
            challenge="challenge_abc",
        )
        assert result is None

    def test_handle_text_message(self):
        """Procesa mensaje de texto correctamente."""
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = self._make_listener(on_message=on_msg)

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "521234567890",
                            "type": "text",
                            "text": {"body": "Hola Mikalia!"},
                            "id": "wamid.abc123",
                        }],
                        "metadata": {"phone_number_id": "phone123"},
                    },
                }],
            }],
        }

        with patch.object(listener, "_mark_as_read"):
            result = listener.handle_webhook_message(payload)

        assert result["processed"] == 1
        assert received == ["Hola Mikalia!"]

    def test_handle_unauthorized_number(self):
        """Numero no autorizado se ignora."""
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = self._make_listener(on_message=on_msg)

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "999999999",
                            "type": "text",
                            "text": {"body": "Hacker!"},
                            "id": "wamid.evil",
                        }],
                    },
                }],
            }],
        }

        result = listener.handle_webhook_message(payload)

        assert result["skipped"] == 1
        assert received == []

    def test_handle_audio_message(self):
        """Audio muestra placeholder (transcripcion pendiente)."""
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = self._make_listener(on_message=on_msg)

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "521234567890",
                            "type": "audio",
                            "audio": {"id": "audio123"},
                            "id": "wamid.audio",
                        }],
                    },
                }],
            }],
        }

        with patch.object(listener, "_mark_as_read"):
            result = listener.handle_webhook_message(payload)

        assert result["processed"] == 1
        assert "Audio" in received[0]

    def test_handle_non_whatsapp_payload(self):
        """Payload que no es de WhatsApp se ignora."""
        listener = self._make_listener()
        result = listener.handle_webhook_message({"object": "page"})
        assert result["processed"] == 0

    def test_handle_empty_entry(self):
        """Payload vacio no crashea."""
        listener = self._make_listener()
        result = listener.handle_webhook_message({
            "object": "whatsapp_business_account",
            "entry": [],
        })
        assert result["processed"] == 0

    @patch("mikalia.notifications.whatsapp.requests.post")
    def test_send_to_allowed_number(self, mock_post):
        """send() envia al primer numero autorizado si no se especifica."""
        mock_post.return_value = MagicMock(
            json=lambda: {"messages": [{"id": "wamid.x"}]},
        )
        mock_post.return_value.raise_for_status = MagicMock()

        listener = self._make_listener()
        result = listener.send("Hola!")

        assert result is True

    def test_send_no_recipient_fails(self):
        """send() sin destinatario y sin allowed_numbers falla."""
        listener = WhatsAppListener(
            phone_number_id="phone123",
            access_token="token_abc",
            verify_token="secret",
            allowed_numbers=[],
        )
        result = listener.send("Hola!")
        assert result is False

    def test_reply_fn_in_callback(self):
        """El reply_fn pasado al callback envia al sender."""
        reply_calls = []

        def on_msg(text, reply_fn):
            reply_calls.append(reply_fn)

        listener = self._make_listener(on_message=on_msg)

        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "521234567890",
                            "type": "text",
                            "text": {"body": "Test"},
                            "id": "wamid.test",
                        }],
                    },
                }],
            }],
        }

        with patch.object(listener, "_mark_as_read"):
            with patch.object(listener, "send", return_value=True) as mock_send:
                listener.handle_webhook_message(payload)

        # Verificar que reply_fn fue capturado
        assert len(reply_calls) == 1
        # Llamar reply_fn deberia enviar al sender
        reply_fn = reply_calls[0]
        with patch.object(listener._channel, "_send_message", return_value=True) as mock_ch:
            reply_fn("Respuesta!")
            mock_ch.assert_called_once_with("Respuesta!", "521234567890")


# ================================================================
# FastAPI WhatsApp endpoints
# ================================================================

class TestWhatsAppAPI:
    @pytest.fixture
    def client(self, tmp_path):
        """Cliente de test con WhatsApp configurado."""
        from fastapi.testclient import TestClient
        from mikalia.core.memory import MemoryManager
        from pathlib import Path

        schema = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"
        db = tmp_path / "test_wa.db"
        mem = MemoryManager(db_path=str(db), schema_path=str(schema))

        listener = WhatsAppListener(
            phone_number_id="phone123",
            access_token="token_abc",
            verify_token="test_verify",
            allowed_numbers=["521234567890"],
        )

        from mikalia.api import create_app
        app = create_app(memory=mem, whatsapp_listener=listener)
        return TestClient(app)

    @pytest.fixture
    def client_no_wa(self, tmp_path):
        """Cliente de test SIN WhatsApp."""
        from fastapi.testclient import TestClient
        from mikalia.core.memory import MemoryManager
        from pathlib import Path

        schema = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"
        db = tmp_path / "test_nowa.db"
        mem = MemoryManager(db_path=str(db), schema_path=str(schema))

        from mikalia.api import create_app
        app = create_app(memory=mem)
        return TestClient(app)

    def test_verify_webhook_success(self, client):
        resp = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test_verify",
                "hub.challenge": "challenge_xyz",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "challenge_xyz"

    def test_verify_webhook_wrong_token(self, client):
        resp = client.get(
            "/webhook/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong",
                "hub.challenge": "challenge_xyz",
            },
        )
        assert resp.status_code == 403

    def test_verify_webhook_no_whatsapp(self, client_no_wa):
        resp = client_no_wa.get(
            "/webhook/whatsapp",
            params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "y"},
        )
        assert resp.status_code == 503

    def test_post_message_webhook(self, client):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "521234567890",
                            "type": "text",
                            "text": {"body": "Hola!"},
                            "id": "wamid.test123",
                        }],
                    },
                }],
            }],
        }

        with patch.object(
            WhatsAppListener, "_mark_as_read"
        ):
            resp = client.post("/webhook/whatsapp", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 1

    def test_post_message_no_whatsapp(self, client_no_wa):
        resp = client_no_wa.post("/webhook/whatsapp", json={})
        assert resp.status_code == 503
