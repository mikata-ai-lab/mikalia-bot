"""
telegram.py — Canal de Telegram para notificaciones de Mikalia.

Implementa NotificationChannel para enviar mensajes al chat
de Mikata-kun via Telegram Bot API.

¿Por qué Telegram?
    - Gratis al 100%
    - API simple y bien documentada
    - Notificaciones push instantáneas al celular
    - Soporta markdown, botones inline, archivos
    - No necesita servidor (solo HTTP POST)

Setup (documentado en docs/SETUP_TELEGRAM.md):
    1. Hablar con @BotFather en Telegram
    2. Crear bot: /newbot → "Mikalia Bot"
    3. Copiar token al .env
    4. Obtener chat_id: hablar al bot, luego /getUpdates
    5. Copiar chat_id al .env

Tipos de mensaje:
    - Texto simple: post publicado, errores
    - Texto + botones inline: PR necesita review [F3]

Formato: Telegram usa "MarkdownV2" que requiere escapar
caracteres especiales. Este módulo maneja el escapado automático.

Uso:
    from mikalia.notifications.telegram import TelegramChannel
    telegram = TelegramChannel(bot_token, chat_id, templates)
    telegram.send(Event.POST_PUBLISHED, {"title": "Mi post", "url": "..."})
"""

from __future__ import annotations

import re
from typing import Any

import requests

from mikalia.notifications.notifier import Event, NotificationChannel
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.telegram")


class TelegramChannel(NotificationChannel):
    """
    Canal de notificación via Telegram Bot API.

    Envía mensajes al chat de Mikata-kun cuando ocurren
    eventos importantes (post publicado, error, etc.)

    Args:
        bot_token: Token del bot de Telegram (de @BotFather)
        chat_id: ID del chat donde enviar mensajes
        templates: Templates de mensajes para cada tipo de evento
    """

    # URL base de la Telegram Bot API
    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        templates: dict[str, str] | None = None,
    ):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_url = self.API_BASE.format(token=bot_token)

        # Templates por defecto para cada evento
        self._templates = templates or {
            Event.POST_PUBLISHED.value: "🌸 ¡Nuevo post publicado!\n📝 {title}\n🔗 {url}",
            Event.PR_CREATED.value: "🔀 PR creado por Mikalia\n📝 {title}\n🔗 {pr_url}",
            Event.REVIEW_NEEDED.value: "👀 Mikalia necesita tu aprobación\n📝 {title}\n🔗 {pr_url}",
            Event.ERROR.value: "⚠️ Error en Mikalia\n❌ {error_message}",
        }

    def send(self, event: Event, data: dict[str, Any]) -> bool:
        """
        Envía una notificación por Telegram.

        Busca el template correspondiente al evento, lo llena
        con los datos proporcionados, y lo envía al chat.

        Args:
            event: Tipo de evento.
            data: Datos para rellenar el template.

        Returns:
            True si el mensaje se envió correctamente.
        """
        # Obtener template para este evento
        template = self._templates.get(event.value)
        if not template:
            logger.warning(f"No hay template para evento: {event.value}")
            return False

        # Rellenar template con datos
        try:
            mensaje = template.format(**data)
        except KeyError as e:
            logger.error(f"Falta dato en notificación: {e}")
            mensaje = f"🌸 Evento: {event.value}\n{data}"

        # Enviar mensaje
        return self._send_message(mensaje)

    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Envía un mensaje de texto al chat configurado.

        Usa HTML en vez de MarkdownV2 porque es más fácil de
        manejar (menos caracteres que escapar).

        Args:
            text: Texto del mensaje.
            parse_mode: Formato ("HTML" o "MarkdownV2").

        Returns:
            True si el envío fue exitoso.
        """
        url = f"{self._api_url}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            if response.json().get("ok"):
                logger.success("Mensaje de Telegram enviado")
                return True
            else:
                logger.error(f"Telegram API error: {response.json()}")
                return False

        except requests.Timeout:
            logger.error("Timeout al enviar mensaje de Telegram")
            return False
        except requests.RequestException as e:
            logger.error(f"Error de conexión con Telegram: {e}")
            return False

    def is_configured(self) -> bool:
        """
        Verifica si el bot de Telegram está configurado.

        Returns:
            True si tenemos token y chat_id.
        """
        return bool(self._bot_token and self._chat_id)

    def test_connection(self) -> bool:
        """
        Prueba la conexión con Telegram enviando un mensaje de test.

        Útil para el comando `mikalia health` que verifica
        que todas las conexiones funcionen.

        Returns:
            True si la conexión funciona.
        """
        return self._send_message("🌸 Mikalia Bot conectada correctamente!")
