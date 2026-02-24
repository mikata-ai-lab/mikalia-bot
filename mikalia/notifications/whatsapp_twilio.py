"""
whatsapp_twilio.py — WhatsApp via Twilio para Mikalia.

Alternativa a Meta Cloud API. Mas facil de configurar,
tiene sandbox que funciona inmediato sin verificacion.

Setup:
    1. Crear cuenta en twilio.com/try-twilio
    2. Ir a Messaging > Try it out > Send a WhatsApp message
    3. Enviar el codigo "join XXXXX" al sandbox number desde tu WhatsApp
    4. Copiar Account SID, Auth Token y Sandbox Number
    5. Agregar al .env:
        TWILIO_ACCOUNT_SID=ACxxxxxxx
        TWILIO_AUTH_TOKEN=xxxxxxx
        TWILIO_WHATSAPP_FROM=+14155238886
        WHATSAPP_RECIPIENT=+521234567890

Uso:
    from mikalia.notifications.whatsapp_twilio import TwilioWhatsApp
    wa = TwilioWhatsApp(account_sid, auth_token, from_number, to_number)
    wa.send_message("Hola Mikata-kun~")
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import requests

from mikalia.notifications.notifier import Event, NotificationChannel
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.whatsapp.twilio")

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class TwilioWhatsApp(NotificationChannel):
    """
    WhatsApp via Twilio API.

    Envia y recibe mensajes de WhatsApp usando Twilio como intermediario.
    Funciona con sandbox (gratis para testing) o numero propio.

    Args:
        account_sid: Twilio Account SID (empieza con AC).
        auth_token: Twilio Auth Token.
        from_number: Numero de WhatsApp de Twilio (sandbox o propio).
        to_number: Numero del destinatario (Mikata-kun).
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_number: str,
        templates: dict[str, str] | None = None,
    ):
        self._sid = account_sid
        self._token = auth_token
        self._from = self._normalize_number(from_number)
        self._to = self._normalize_number(to_number)
        self._api_url = TWILIO_API.format(sid=account_sid)

        self._templates = templates or {
            Event.POST_PUBLISHED.value: "Nuevo post publicado!\n{title}\n{url}",
            Event.PR_CREATED.value: "PR creado por Mikalia\n{title}\n{pr_url}",
            Event.REVIEW_NEEDED.value: "Mikalia necesita tu aprobacion\n{title}\n{pr_url}",
            Event.ERROR.value: "Error en Mikalia\n{error_message}",
        }

    @staticmethod
    def _normalize_number(number: str) -> str:
        """Asegura formato whatsapp:+XXXXXXXXXXX."""
        number = number.strip()
        if number.startswith("whatsapp:"):
            return number
        if not number.startswith("+"):
            number = f"+{number}"
        return f"whatsapp:{number}"

    def send(self, event: Event, data: dict[str, Any]) -> bool:
        """Envia notificacion por WhatsApp via Twilio."""
        template = self._templates.get(event.value)
        if not template:
            logger.warning(f"No hay template para evento: {event.value}")
            return False

        try:
            mensaje = template.format(**data)
        except KeyError as e:
            logger.error(f"Falta dato en notificacion: {e}")
            mensaje = f"Evento: {event.value}\n{data}"

        return self.send_message(mensaje)

    def send_message(self, text: str, to: str | None = None) -> bool:
        """
        Envia mensaje de texto por WhatsApp via Twilio.

        Args:
            text: Texto del mensaje (max 1600 chars).
            to: Numero destino (default: el configurado).

        Returns:
            True si el envio fue exitoso.
        """
        recipient = self._normalize_number(to) if to else self._to
        payload = {
            "From": self._from,
            "To": recipient,
            "Body": text[:1600],
        }

        try:
            resp = requests.post(
                self._api_url,
                data=payload,
                auth=(self._sid, self._token),
                timeout=10,
            )

            if resp.status_code in (200, 201):
                data = resp.json()
                sid = data.get("sid", "?")
                logger.success(f"WhatsApp (Twilio) enviado: {sid}")
                return True
            else:
                logger.error(f"Twilio error {resp.status_code}: {resp.text[:200]}")
                return False

        except requests.Timeout:
            logger.error("Timeout enviando WhatsApp via Twilio")
            return False
        except requests.RequestException as e:
            logger.error(f"Error de conexion con Twilio: {e}")
            return False

    def is_configured(self) -> bool:
        """Verifica si Twilio esta configurado."""
        return bool(self._sid and self._token and self._from and self._to)

    def test_connection(self) -> bool:
        """Prueba la conexion enviando mensaje de test."""
        return self.send_message("Mikalia conectada via Twilio~")


class TwilioWhatsAppListener:
    """
    Escucha mensajes de WhatsApp via webhooks de Twilio.

    Twilio envia un POST form-encoded a nuestro FastAPI server
    cuando llega un mensaje al numero de WhatsApp.

    Payload de Twilio (form-encoded):
        From=whatsapp:+521234567890
        To=whatsapp:+14155238886
        Body=Hola Mikalia!
        MessageSid=SMxxxxxxx
        NumMedia=0

    Args:
        account_sid: Twilio Account SID.
        auth_token: Twilio Auth Token.
        from_number: Numero de WhatsApp de Twilio.
        allowed_numbers: Numeros autorizados.
        on_message: Callback (texto, reply_fn).
    """

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        allowed_numbers: list[str] | None = None,
        on_message: Any = None,
    ):
        self._sid = account_sid
        self._token = auth_token
        self._channel = TwilioWhatsApp(account_sid, auth_token, from_number, "")
        self._from = self._channel._normalize_number(from_number)
        self._allowed_numbers = set(allowed_numbers or [])
        self._on_message = on_message

    def send(self, text: str, recipient: str | None = None) -> bool:
        """Envia mensaje al numero dado."""
        if not recipient and self._allowed_numbers:
            recipient = next(iter(self._allowed_numbers))
        if not recipient:
            logger.error("No hay destinatario para enviar mensaje")
            return False
        return self._channel.send_message(text, to=recipient)

    def send_typing(self, recipient: str | None = None) -> bool:
        """Twilio no soporta typing indicator."""
        return True

    def handle_webhook(self, form_data: dict) -> dict:
        """
        Procesa un mensaje entrante del webhook de Twilio.

        Args:
            form_data: Datos form-encoded del POST de Twilio.

        Returns:
            Dict con info del procesamiento.
        """
        result = {"processed": 0, "skipped": 0, "errors": 0}

        sender_raw = form_data.get("From", "")
        body = form_data.get("Body", "").strip()
        _msg_sid = form_data.get("MessageSid", "")  # noqa: F841

        # Extraer numero sin prefijo "whatsapp:"
        sender = sender_raw.replace("whatsapp:", "").lstrip("+")

        if not body:
            result["skipped"] += 1
            return result

        # Verificar numero autorizado
        if self._allowed_numbers and sender not in self._allowed_numbers:
            logger.warning(f"WhatsApp de numero no autorizado: {sender}")
            result["skipped"] += 1
            return result

        logger.info(f"WhatsApp (Twilio) de {sender}: {body[:50]}...")

        try:
            if self._on_message:
                def reply_fn(response_text: str) -> bool:
                    return self.send(response_text, recipient=sender)

                self._on_message(body, reply_fn)

            result["processed"] += 1
        except Exception as e:
            logger.error(f"Error procesando mensaje Twilio: {e}")
            result["errors"] += 1

        return result

    def validate_signature(
        self, url: str, params: dict, signature: str,
    ) -> bool:
        """
        Valida la firma de Twilio para seguridad del webhook.

        Twilio firma cada request con HMAC-SHA1 usando el Auth Token.
        Esto previene que alguien envie mensajes falsos al webhook.

        Args:
            url: URL completa del webhook.
            params: Parametros del POST (form data).
            signature: Valor del header X-Twilio-Signature.

        Returns:
            True si la firma es valida.
        """
        # Construir string para firmar: URL + params ordenados
        data = url
        for key in sorted(params.keys()):
            data += key + params[key]

        expected = hmac.new(
            self._token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        ).digest()

        import base64
        expected_b64 = base64.b64encode(expected).decode("utf-8")

        return hmac.compare_digest(expected_b64, signature)
