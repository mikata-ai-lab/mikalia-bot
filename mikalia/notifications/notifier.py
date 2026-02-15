"""
notifier.py — Sistema de notificaciones genérico de Mikalia.

Patrón Strategy: define una interfaz que cualquier canal de
notificación puede implementar. Hoy es Telegram, mañana podría
ser Discord, Slack, email, etc.

¿Por qué abstraer?
    Porque no queremos que el código del bot esté acoplado a Telegram.
    Si mañana Mikata quiere cambiar a Discord, solo agrega un nuevo
    adapter sin tocar el código existente.

¿Qué es el patrón Strategy?
    Es un patrón de diseño donde defines una "familia" de algoritmos
    (en este caso, formas de notificar) intercambiables. El código
    que usa el notificador no sabe ni le importa si va por Telegram,
    Discord, o paloma mensajera.

Uso:
    from mikalia.notifications.notifier import Notifier, Event
    from mikalia.notifications.telegram import TelegramChannel

    notifier = Notifier(channels=[TelegramChannel(config)])
    notifier.notify(Event.POST_PUBLISHED, {"title": "Mi post", "url": "..."})
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.notifications")


class Event(Enum):
    """
    Tipos de eventos que Mikalia puede notificar.

    Cada evento tiene un significado específico:
    - POST_PUBLISHED: Un nuevo post fue publicado exitosamente
    - PR_CREATED: Se creó un Pull Request [F3]
    - REVIEW_NEEDED: Se necesita aprobación humana [F3]
    - ERROR: Algo falló y requiere atención
    """
    POST_PUBLISHED = "post_published"
    PR_CREATED = "pr_created"
    REVIEW_NEEDED = "review_needed"
    ERROR = "error"


class NotificationChannel(ABC):
    """
    Interfaz abstracta para un canal de notificación.

    Cualquier canal (Telegram, Discord, email) debe implementar
    este método send(). Esto es el patrón Strategy en acción.

    ¿Qué es ABC (Abstract Base Class)?
    Es la forma de Python de definir una "interfaz" — una clase
    que NO se puede instanciar directamente, solo heredar.
    Las clases hijas DEBEN implementar los métodos abstractos.
    """

    @abstractmethod
    def send(self, event: Event, data: dict[str, Any]) -> bool:
        """
        Envía una notificación por este canal.

        Args:
            event: Tipo de evento a notificar.
            data: Datos asociados al evento (título, URL, error, etc.)

        Returns:
            True si el envío fue exitoso, False si falló.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """
        Verifica si el canal está configurado correctamente.

        Returns:
            True si la configuración es válida.
        """
        ...


class Notifier:
    """
    Gestor central de notificaciones de Mikalia.

    Mantiene una lista de canales y envía eventos a todos los
    que estén configurados y activos. Si un canal falla, los
    demás siguen funcionando (no bloquea).

    Args:
        channels: Lista de canales de notificación configurados.
        enabled_events: Lista de tipos de evento habilitados.
    """

    def __init__(
        self,
        channels: list[NotificationChannel] | None = None,
        enabled_events: list[str] | None = None,
    ):
        self._channels = channels or []
        self._enabled_events = set(enabled_events or [e.value for e in Event])

    def notify(self, event: Event, data: dict[str, Any]) -> None:
        """
        Envía una notificación a todos los canales configurados.

        Si un canal falla, loggea el error pero NO detiene los demás.
        Las notificaciones nunca deben bloquear el flujo principal.

        Args:
            event: Tipo de evento.
            data: Datos del evento.
        """
        # Verificar si este tipo de evento está habilitado
        if event.value not in self._enabled_events:
            logger.info(f"Evento {event.value} no está habilitado, omitiendo notificación")
            return

        # Enviar a cada canal configurado
        for channel in self._channels:
            if not channel.is_configured():
                continue

            try:
                exito = channel.send(event, data)
                if exito:
                    logger.info(f"Notificación enviada: {event.value}")
                else:
                    logger.warning(
                        f"Notificación falló en {channel.__class__.__name__}"
                    )
            except Exception as e:
                # Las notificaciones NUNCA deben crashear el bot
                logger.error(
                    f"Error en notificación ({channel.__class__.__name__}): {e}"
                )

    def add_channel(self, channel: NotificationChannel) -> None:
        """Agrega un canal de notificación."""
        self._channels.append(channel)
