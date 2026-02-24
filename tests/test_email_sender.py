"""
test_email_sender.py — Tests para EmailSenderTool.

Verifica:
- Envio exitoso (mock smtplib)
- SMTP no configurado
- Email invalido
- Subject vacio
- Email HTML
- Error de autenticacion
- Definicion Claude correcta
"""

from __future__ import annotations

import smtplib
import pytest
from unittest.mock import patch, MagicMock

from mikalia.tools.email_sender import EmailSenderTool


# Env vars comunes para SMTP configurado
SMTP_ENV = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "mikalia@gmail.com",
    "SMTP_PASSWORD": "app_password_123",
    "SMTP_FROM": "mikalia@gmail.com",
}


# ================================================================
# EmailSenderTool
# ================================================================

class TestEmailSenderTool:

    @patch("mikalia.tools.email_sender.smtplib.SMTP")
    def test_send_success(self, mock_smtp_cls):
        """Envio exitoso de email con SMTP configurado."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        tool = EmailSenderTool()

        with patch.dict("os.environ", SMTP_ENV):
            result = tool.execute(
                to="mikata@example.com",
                subject="Test Email",
                body="Hello from Mikalia!",
            )

        assert result.success
        assert "mikata@example.com" in result.output
        assert "Test Email" in result.output
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("mikalia@gmail.com", "app_password_123")
        mock_server.send_message.assert_called_once()

    def test_missing_smtp_config(self):
        """Sin SMTP configurado retorna error claro."""
        tool = EmailSenderTool()

        with patch.dict("os.environ", {}, clear=True):
            result = tool.execute(
                to="test@example.com",
                subject="Test",
                body="Hello",
            )

        assert not result.success
        assert "SMTP" in result.error

    def test_invalid_email_address(self):
        """Email sin @ retorna error de validacion."""
        tool = EmailSenderTool()

        with patch.dict("os.environ", SMTP_ENV):
            result = tool.execute(
                to="not-a-valid-email",
                subject="Test",
                body="Hello",
            )

        assert not result.success
        assert "invalido" in result.error.lower() or "invalid" in result.error.lower()

    def test_empty_subject(self):
        """Subject vacio retorna error."""
        tool = EmailSenderTool()

        with patch.dict("os.environ", SMTP_ENV):
            result = tool.execute(
                to="test@example.com",
                subject="   ",
                body="Hello",
            )

        assert not result.success
        assert "vacio" in result.error.lower() or "subject" in result.error.lower()

    @patch("mikalia.tools.email_sender.smtplib.SMTP")
    def test_html_email(self, mock_smtp_cls):
        """Email HTML se envia con content-type html."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        tool = EmailSenderTool()

        with patch.dict("os.environ", SMTP_ENV):
            result = tool.execute(
                to="test@example.com",
                subject="HTML Test",
                body="<h1>Hello</h1><p>From Mikalia</p>",
                html=True,
            )

        assert result.success
        # Verificar que send_message fue llamado con un mensaje
        send_call = mock_server.send_message.call_args[0][0]
        payload = send_call.get_payload()
        # El payload es una lista con un MIMEText attachment
        assert len(payload) >= 1
        content_type = payload[0].get_content_type()
        assert content_type == "text/html"

    @patch("mikalia.tools.email_sender.smtplib.SMTP")
    def test_auth_error(self, mock_smtp_cls):
        """Error de autenticacion SMTP retorna error claro."""
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"Authentication failed"
        )
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        tool = EmailSenderTool()

        with patch.dict("os.environ", SMTP_ENV):
            result = tool.execute(
                to="test@example.com",
                subject="Test",
                body="Hello",
            )

        assert not result.success
        assert "autenticacion" in result.error.lower() or "authentication" in result.error.lower()

    def test_tool_metadata(self):
        """Tool tiene nombre, descripcion y parametros correctos."""
        tool = EmailSenderTool()

        assert tool.name == "email_send"
        assert "email" in tool.description.lower() or "SMTP" in tool.description

        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "to" in params["properties"]
        assert "subject" in params["properties"]
        assert "body" in params["properties"]
        assert "html" in params["properties"]
        assert "to" in params["required"]
        assert "subject" in params["required"]
        assert "body" in params["required"]

        defn = tool.to_claude_definition()
        assert defn["name"] == "email_send"
        assert "input_schema" in defn
        assert "description" in defn
