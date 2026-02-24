"""
test_whatsapp_twilio.py — Tests para integracion WhatsApp via Twilio.

Verifica:
- TwilioWhatsApp: envio de mensajes
- TwilioWhatsAppListener: procesamiento de webhooks
- Seguridad: numeros autorizados, firma Twilio
- Endpoints FastAPI para Twilio
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from mikalia.notifications.whatsapp_twilio import (
    TwilioWhatsApp,
    TwilioWhatsAppListener,
    TWILIO_API,
)
from mikalia.notifications.notifier import Event


# ================================================================
# TwilioWhatsApp (envio de mensajes)
# ================================================================

class TestTwilioWhatsApp:
    def test_is_configured_true(self):
        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        assert wa.is_configured()

    def test_is_configured_false(self):
        wa = TwilioWhatsApp("", "token", "+14155238886", "+521234567890")
        assert not wa.is_configured()

    def test_normalize_number_plain(self):
        assert TwilioWhatsApp._normalize_number("521234567890") == "whatsapp:+521234567890"

    def test_normalize_number_with_plus(self):
        assert TwilioWhatsApp._normalize_number("+521234567890") == "whatsapp:+521234567890"

    def test_normalize_number_already_whatsapp(self):
        assert TwilioWhatsApp._normalize_number("whatsapp:+521234567890") == "whatsapp:+521234567890"

    @patch("mikalia.notifications.whatsapp_twilio.requests.post")
    def test_send_message_success(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"sid": "SM123", "status": "queued"},
        )

        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        result = wa.send_message("Hola!")

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["auth"] == ("AC123", "token")
        payload = call_args.kwargs["data"]
        assert payload["From"] == "whatsapp:+14155238886"
        assert payload["To"] == "whatsapp:+521234567890"
        assert payload["Body"] == "Hola!"

    @patch("mikalia.notifications.whatsapp_twilio.requests.post")
    def test_send_message_failure(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=400,
            text="Bad request",
        )

        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        result = wa.send_message("Hola!")

        assert result is False

    @patch("mikalia.notifications.whatsapp_twilio.requests.post")
    def test_send_message_timeout(self, mock_post):
        import requests as req
        mock_post.side_effect = req.Timeout("timeout")

        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        result = wa.send_message("Hola!")

        assert result is False

    @patch("mikalia.notifications.whatsapp_twilio.requests.post")
    def test_send_event(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"sid": "SM123"},
        )

        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        result = wa.send(Event.POST_PUBLISHED, {"title": "Test", "url": "http://x.com"})

        assert result is True

    def test_send_unknown_event(self):
        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        with patch.object(wa, "_templates", {}):
            result = wa.send(Event.POST_PUBLISHED, {})
            assert result is False

    @patch("mikalia.notifications.whatsapp_twilio.requests.post")
    def test_send_message_truncates_long_text(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"sid": "SM123"},
        )

        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        wa.send_message("x" * 2000)

        payload = mock_post.call_args.kwargs["data"]
        assert len(payload["Body"]) == 1600

    @patch("mikalia.notifications.whatsapp_twilio.requests.post")
    def test_send_to_custom_recipient(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"sid": "SM123"},
        )

        wa = TwilioWhatsApp("AC123", "token", "+14155238886", "+521234567890")
        wa.send_message("Hola!", to="+529999999999")

        payload = mock_post.call_args.kwargs["data"]
        assert payload["To"] == "whatsapp:+529999999999"


# ================================================================
# TwilioWhatsAppListener (webhook)
# ================================================================

class TestTwilioWhatsAppListener:
    def _make_listener(self, **kwargs):
        return TwilioWhatsAppListener(
            account_sid="AC123",
            auth_token="token",
            from_number="+14155238886",
            allowed_numbers=["521234567890"],
            **kwargs,
        )

    def test_handle_text_message(self):
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = self._make_listener(on_message=on_msg)

        form_data = {
            "From": "whatsapp:+521234567890",
            "To": "whatsapp:+14155238886",
            "Body": "Hola Mikalia!",
            "MessageSid": "SM123",
        }

        result = listener.handle_webhook(form_data)

        assert result["processed"] == 1
        assert received == ["Hola Mikalia!"]

    def test_handle_unauthorized_number(self):
        received = []

        def on_msg(text, reply_fn):
            received.append(text)

        listener = self._make_listener(on_message=on_msg)

        form_data = {
            "From": "whatsapp:+999999999",
            "Body": "Hacker!",
            "MessageSid": "SM666",
        }

        result = listener.handle_webhook(form_data)

        assert result["skipped"] == 1
        assert received == []

    def test_handle_empty_body(self):
        listener = self._make_listener()

        form_data = {
            "From": "whatsapp:+521234567890",
            "Body": "",
            "MessageSid": "SM123",
        }

        result = listener.handle_webhook(form_data)
        assert result["skipped"] == 1

    def test_reply_fn_sends_to_sender(self):
        reply_fns = []

        def on_msg(text, reply_fn):
            reply_fns.append(reply_fn)

        listener = self._make_listener(on_message=on_msg)

        form_data = {
            "From": "whatsapp:+521234567890",
            "Body": "Test",
            "MessageSid": "SM123",
        }

        listener.handle_webhook(form_data)

        assert len(reply_fns) == 1
        with patch.object(listener._channel, "send_message", return_value=True) as mock:
            reply_fns[0]("Respuesta!")
            mock.assert_called_once_with("Respuesta!", to="521234567890")

    def test_send_no_recipient_fails(self):
        listener = TwilioWhatsAppListener(
            account_sid="AC123",
            auth_token="token",
            from_number="+14155238886",
            allowed_numbers=[],
        )
        result = listener.send("Hola!")
        assert result is False

    @patch("mikalia.notifications.whatsapp_twilio.requests.post")
    def test_send_to_first_allowed(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"sid": "SM123"},
        )

        listener = self._make_listener()
        result = listener.send("Hola!")

        assert result is True

    def test_send_typing_always_true(self):
        listener = self._make_listener()
        assert listener.send_typing() is True


# ================================================================
# FastAPI Twilio endpoint
# ================================================================

class TestTwilioAPI:
    @pytest.fixture
    def client(self, tmp_path):
        from fastapi.testclient import TestClient
        from mikalia.core.memory import MemoryManager
        from pathlib import Path

        schema = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"
        db = tmp_path / "test_tw.db"
        mem = MemoryManager(db_path=str(db), schema_path=str(schema))

        listener = TwilioWhatsAppListener(
            account_sid="AC123",
            auth_token="token",
            from_number="+14155238886",
            allowed_numbers=["521234567890"],
        )

        from mikalia.api import create_app
        app = create_app(memory=mem, twilio_listener=listener)
        return TestClient(app)

    @pytest.fixture
    def client_no_twilio(self, tmp_path):
        from fastapi.testclient import TestClient
        from mikalia.core.memory import MemoryManager
        from pathlib import Path

        schema = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"
        db = tmp_path / "test_notw.db"
        mem = MemoryManager(db_path=str(db), schema_path=str(schema))

        from mikalia.api import create_app
        app = create_app(memory=mem)
        return TestClient(app)

    def test_twilio_webhook_processes_message(self, client):
        resp = client.post(
            "/webhook/twilio",
            data={
                "From": "whatsapp:+521234567890",
                "To": "whatsapp:+14155238886",
                "Body": "Hola!",
                "MessageSid": "SM123",
            },
        )
        assert resp.status_code == 200
        assert "<Response>" in resp.text

    def test_twilio_webhook_not_configured(self, client_no_twilio):
        resp = client_no_twilio.post(
            "/webhook/twilio",
            data={"From": "x", "Body": "y"},
        )
        assert resp.status_code == 503
