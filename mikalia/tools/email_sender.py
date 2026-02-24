"""
email_sender.py — Envio de emails para Mikalia.

Usa SMTP (stdlib, sin dependencias extra).
Soporta Gmail, Outlook, y cualquier servidor SMTP.

Config en .env:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USER=tu@gmail.com
    SMTP_PASSWORD=tu_app_password
    SMTP_FROM=tu@gmail.com
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.email_sender")


class EmailSenderTool(BaseTool):
    """Envia emails via SMTP."""

    @property
    def name(self) -> str:
        return "email_send"

    @property
    def description(self) -> str:
        return (
            "Send an email via SMTP. Requires SMTP configuration in .env "
            "(SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM). "
            "Supports plain text and HTML emails."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject",
                },
                "body": {
                    "type": "string",
                    "description": "Email body (plain text or HTML)",
                },
                "html": {
                    "type": "boolean",
                    "description": "Send as HTML (default: false)",
                },
            },
            "required": ["to", "subject", "body"],
        }

    def execute(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
        **_: Any,
    ) -> ToolResult:
        # Leer config de env
        host = os.environ.get("SMTP_HOST", "")
        port = int(os.environ.get("SMTP_PORT", "587"))
        user = os.environ.get("SMTP_USER", "")
        password = os.environ.get("SMTP_PASSWORD", "")
        from_addr = os.environ.get("SMTP_FROM", user)

        if not all([host, user, password]):
            return ToolResult(
                success=False,
                error=(
                    "SMTP no configurado. Agrega al .env: "
                    "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD"
                ),
            )

        if not to or "@" not in to:
            return ToolResult(success=False, error=f"Email invalido: {to}")

        if not subject.strip():
            return ToolResult(success=False, error="Subject vacio")

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = from_addr
            msg["To"] = to
            msg["Subject"] = subject

            content_type = "html" if html else "plain"
            msg.attach(MIMEText(body, content_type, "utf-8"))

            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)

            logger.success(f"Email enviado a {to}: {subject}")
            return ToolResult(
                success=True,
                output=f"Email enviado exitosamente a {to}\nSubject: {subject}",
            )
        except smtplib.SMTPAuthenticationError:
            return ToolResult(
                success=False,
                error="Error de autenticacion SMTP. Verifica user/password en .env",
            )
        except smtplib.SMTPException as e:
            return ToolResult(success=False, error=f"Error SMTP: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"Error enviando email: {e}")
