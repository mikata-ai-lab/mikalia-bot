"""
whatsapp.py — Canal de WhatsApp para Mikalia.

Implementa NotificationChannel + WhatsAppListener para comunicacion
bidireccional via Meta Cloud API (WhatsApp Business).

Setup:
    1. Crear app en developers.facebook.com
    2. Agregar producto "WhatsApp"
    3. Obtener Phone Number ID y Access Token
    4. Configurar webhook URL: https://tu-vps/webhook/whatsapp
    5. Agregar variables al .env:
        WHATSAPP_PHONE_ID=123456789
        WHATSAPP_ACCESS_TOKEN=EAAxxxxxxx
        WHATSAPP_VERIFY_TOKEN=mi_token_secreto
        WHATSAPP_RECIPIENT=521234567890

Uso:
    from mikalia.notifications.whatsapp import WhatsAppChannel, WhatsAppListener
    channel = WhatsAppChannel(phone_id, access_token, recipient)
    channel.send(Event.POST_PUBLISHED, {"title": "Mi post", "url": "..."})
"""

from __future__ import annotations

import time
from typing import Any

import requests

from mikalia.notifications.notifier import Event, NotificationChannel
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.whatsapp")

# Meta Graph API version
API_VERSION = "v21.0"
API_BASE = f"https://graph.facebook.com/{API_VERSION}"


class WhatsAppChannel(NotificationChannel):
    """
    Canal de notificacion via WhatsApp Business API (Meta Cloud).

    Envia mensajes de texto al numero de Mikata-kun.

    Args:
        phone_number_id: ID del numero de telefono de WhatsApp Business.
        access_token: Token de acceso permanente de la app.
        recipient_phone: Numero del destinatario (con codigo de pais, ej: 521234567890).
        templates: Templates de mensajes para cada tipo de evento.
    """

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        recipient_phone: str,
        templates: dict[str, str] | None = None,
    ):
        self._phone_id = phone_number_id
        self._access_token = access_token
        self._recipient = recipient_phone

        self._templates = templates or {
            Event.POST_PUBLISHED.value: "Nuevo post publicado!\n{title}\n{url}",
            Event.PR_CREATED.value: "PR creado por Mikalia\n{title}\n{pr_url}",
            Event.REVIEW_NEEDED.value: "Mikalia necesita tu aprobacion\n{title}\n{pr_url}",
            Event.ERROR.value: "Error en Mikalia\n{error_message}",
        }

    def send(self, event: Event, data: dict[str, Any]) -> bool:
        """Envia notificacion por WhatsApp."""
        template = self._templates.get(event.value)
        if not template:
            logger.warning(f"No hay template para evento: {event.value}")
            return False

        try:
            mensaje = template.format(**data)
        except KeyError as e:
            logger.error(f"Falta dato en notificacion: {e}")
            mensaje = f"Evento: {event.value}\n{data}"

        return self._send_message(mensaje)

    def _send_message(self, text: str, recipient: str | None = None) -> bool:
        """
        Envia un mensaje de texto via WhatsApp API.

        Args:
            text: Texto del mensaje.
            recipient: Numero destino (default: el configurado).

        Returns:
            True si el envio fue exitoso.
        """
        to = recipient or self._recipient
        url = f"{API_BASE}/{self._phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()

            data = resp.json()
            if data.get("messages"):
                logger.success(f"WhatsApp mensaje enviado a {to}")
                return True
            else:
                logger.error(f"WhatsApp API sin messages: {data}")
                return False

        except requests.Timeout:
            logger.error("Timeout enviando mensaje de WhatsApp")
            return False
        except requests.RequestException as e:
            logger.error(f"Error de conexion con WhatsApp: {e}")
            return False

    def is_configured(self) -> bool:
        """Verifica si WhatsApp esta configurado."""
        return bool(self._phone_id and self._access_token and self._recipient)

    def test_connection(self) -> bool:
        """Prueba la conexion enviando mensaje de test."""
        return self._send_message("Mikalia conectada a WhatsApp correctamente~")


class WhatsAppListener:
    """
    Escucha mensajes de WhatsApp via webhooks y responde.

    A diferencia de Telegram (long polling), WhatsApp usa webhooks:
    Meta envia un POST a nuestro FastAPI server cuando llega un mensaje.

    Args:
        phone_number_id: ID del numero de WhatsApp Business.
        access_token: Token de acceso.
        verify_token: Token para verificacion de webhook (lo defines tu).
        allowed_numbers: Numeros autorizados (seguridad).
        on_message: Callback que recibe (texto, sender, reply_fn).
    """

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        verify_token: str,
        allowed_numbers: list[str] | None = None,
        on_message: Any = None,
    ):
        self._phone_id = phone_number_id
        self._access_token = access_token
        self._verify_token = verify_token
        self._allowed_numbers = set(allowed_numbers or [])
        self._on_message = on_message
        self._channel = WhatsAppChannel(phone_number_id, access_token, "")

    @property
    def verify_token(self) -> str:
        """Token de verificacion para el webhook."""
        return self._verify_token

    def send(self, text: str, recipient: str | None = None) -> bool:
        """Envia mensaje al numero dado (o al ultimo que escribio)."""
        if not recipient and self._allowed_numbers:
            recipient = next(iter(self._allowed_numbers))
        if not recipient:
            logger.error("No hay destinatario para enviar mensaje")
            return False
        return self._channel._send_message(text, recipient)

    def send_typing(self, recipient: str | None = None) -> bool:
        """
        Envia indicador de 'typing' en WhatsApp (mark as read).

        WhatsApp no tiene typing indicator como tal, pero podemos
        marcar como leido para dar feedback visual.
        """
        if not recipient and self._allowed_numbers:
            recipient = next(iter(self._allowed_numbers))
        # WhatsApp no tiene typing — usamos read receipt como alternativa
        return True

    def handle_webhook_verify(self, mode: str, token: str, challenge: str) -> str | None:
        """
        Maneja la verificacion del webhook (GET request de Meta).

        Meta envia: hub.mode=subscribe, hub.verify_token=tu_token, hub.challenge=xyz
        Debemos responder con el challenge si el token es correcto.

        Returns:
            El challenge si es valido, None si no.
        """
        if mode == "subscribe" and token == self._verify_token:
            logger.success("Webhook de WhatsApp verificado")
            return challenge

        logger.warning(f"Verificacion de webhook fallida: mode={mode}")
        return None

    def handle_webhook_message(self, payload: dict) -> dict:
        """
        Procesa un mensaje entrante del webhook de WhatsApp.

        Estructura del payload de Meta:
        {
          "object": "whatsapp_business_account",
          "entry": [{
            "changes": [{
              "value": {
                "messages": [{
                  "from": "521234567890",
                  "type": "text",
                  "text": {"body": "Hola!"},
                  "id": "wamid.xxx"
                }],
                "metadata": {"phone_number_id": "123456"}
              }
            }]
          }]
        }

        Returns:
            Dict con info del procesamiento.
        """
        result = {"processed": 0, "skipped": 0, "errors": 0}

        if payload.get("object") != "whatsapp_business_account":
            return result

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])

                for msg in messages:
                    try:
                        self._process_message(msg, result)
                    except Exception as e:
                        logger.error(f"Error procesando mensaje WhatsApp: {e}")
                        result["errors"] += 1

        return result

    def _process_message(self, msg: dict, result: dict) -> None:
        """Procesa un mensaje individual."""
        sender = msg.get("from", "")
        msg_type = msg.get("type", "")
        msg_id = msg.get("id", "")

        # Solo procesar mensajes de numeros autorizados
        if self._allowed_numbers and sender not in self._allowed_numbers:
            logger.warning(f"Mensaje de numero no autorizado: {sender}")
            result["skipped"] += 1
            return

        # Extraer texto segun tipo de mensaje
        text = ""
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "").strip()
        elif msg_type == "audio":
            # TODO: Integrar con SpeechToTextTool para transcribir audio
            text = "[Audio recibido — transcripcion pendiente]"
        elif msg_type == "image":
            text = "[Imagen recibida]"
        else:
            text = f"[Mensaje tipo '{msg_type}' no soportado aun]"

        if not text:
            result["skipped"] += 1
            return

        logger.info(f"WhatsApp de {sender}: {text[:50]}...")

        # Marcar como leido
        self._mark_as_read(msg_id)

        # Llamar callback
        if self._on_message:
            def reply_fn(response_text: str) -> bool:
                return self.send(response_text, recipient=sender)

            self._on_message(text, reply_fn)

        result["processed"] += 1

    def _mark_as_read(self, message_id: str) -> None:
        """Marca un mensaje como leido (doble check azul)."""
        url = f"{API_BASE}/{self._phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        try:
            requests.post(url, json=payload, headers=headers, timeout=5)
        except Exception:
            pass
