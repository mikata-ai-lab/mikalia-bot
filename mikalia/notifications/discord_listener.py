"""
discord_listener.py — Escucha mensajes de Discord y responde.

Convierte a Mikalia en un chatbot interactivo via Discord.
Mikata-kun puede pedirle cosas escribiendole en el canal autorizado.

Arquitectura:
    - Usa discord.py con Intents (message_content=True)
    - Procesa solo mensajes del channel_id configurado (seguridad)
    - Ignora sus propios mensajes
    - Divide mensajes largos en chunks de 2000 caracteres (limite de Discord)

Uso:
    from mikalia.notifications.discord_listener import DiscordListener
    listener = DiscordListener(bot_token, channel_id, on_message=callback)
    listener.listen()
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.notifications.discord")

MAX_MESSAGE_LENGTH = 2000

try:
    import discord
except ImportError:
    discord = None  # type: ignore[assignment]
    logger.warning(
        "discord.py no esta instalado. Instala con: pip install discord.py"
    )


class DiscordListener:
    """
    Escucha mensajes de Discord y ejecuta comandos de Mikalia.

    Solo procesa mensajes del channel_id autorizado.
    Ignora mensajes propios del bot.

    Args:
        bot_token: Token del bot de Discord.
        channel_id: ID del canal autorizado (int o str).
        on_message: Callback que recibe (texto, reply_fn).
    """

    def __init__(
        self,
        bot_token: str,
        channel_id: int | str,
        on_message: Callable[[str, Callable], None] | None = None,
    ):
        if discord is None:
            raise RuntimeError(
                "discord.py no esta instalado. "
                "Instala con: pip install discord.py"
            )

        self._bot_token = bot_token
        self._channel_id = int(channel_id)
        self._on_message = on_message

        intents = discord.Intents.default()
        intents.message_content = True
        self._bot = discord.Client(intents=intents)
        self._channel: Any = None

        self._register_events()

    # ----------------------------------------------------------
    # Eventos
    # ----------------------------------------------------------

    def _register_events(self) -> None:
        """Registra los event handlers del bot."""

        @self._bot.event
        async def on_ready() -> None:
            logger.info(f"Bot conectado como {self._bot.user}")
            self._channel = self._bot.get_channel(self._channel_id)

        @self._bot.event
        async def on_message(message: Any) -> None:
            if message.author == self._bot.user:
                return
            if message.channel.id != self._channel_id:
                return
            if self._channel is None:
                self._channel = message.channel

            text = message.content.strip()
            if not text:
                return

            logger.info(f"Mensaje de {message.author}: {text[:80]}")

            if self._on_message:
                reply_fn = self._make_reply_fn(message.channel)
                self._on_message(text, reply_fn)

    def _make_reply_fn(self, channel: Any) -> Callable[[str], None]:
        """Crea una funcion reply sincrona para el callback."""

        def reply(text: str) -> None:
            asyncio.run_coroutine_threadsafe(
                self._async_send(text, channel), self._bot.loop,
            )

        return reply

    # ----------------------------------------------------------
    # API publica
    # ----------------------------------------------------------

    def listen(self) -> None:
        """Inicia el bot de Discord (bloqueante)."""
        logger.info("Iniciando bot de Discord...")
        self._bot.run(self._bot_token)

    async def _async_send(self, text: str, channel: Any = None) -> None:
        """Envia un mensaje, dividiendo en chunks si es necesario."""
        target = channel or self._channel
        if not target:
            logger.error("No hay canal destino para enviar mensaje")
            return

        if len(text) <= MAX_MESSAGE_LENGTH:
            await target.send(text)
            return

        for i in range(0, len(text), MAX_MESSAGE_LENGTH):
            await target.send(text[i : i + MAX_MESSAGE_LENGTH])

    def send(self, text: str, channel: Any = None) -> None:
        """Envia mensaje al canal autorizado (sincrono)."""
        fut = asyncio.run_coroutine_threadsafe(
            self._async_send(text, channel), self._bot.loop,
        )
        fut.result(timeout=10)

    def send_typing(self) -> None:
        """Envia indicador de 'typing...' al canal autorizado."""
        target = self._channel
        if not target:
            return
        fut = asyncio.run_coroutine_threadsafe(
            target.typing(), self._bot.loop,
        )
        fut.result(timeout=5)
