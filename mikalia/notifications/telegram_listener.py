"""
telegram_listener.py — Escucha mensajes de Telegram y responde.

Convierte a Mikalia en un chatbot interactivo via Telegram.
Mikata-kun puede pedirle cosas escribiéndole directamente al bot.

Comandos soportados:
    /start          → Saludo inicial
    /help           → Lista de comandos
    /status         → Estado del bot y config
    post <tema>     → Genera un post (preview, pide confirmación)
    publica         → Publica el último post generado
    hola / hi       → Saludo casual

Arquitectura:
    - Long polling via getUpdates (no necesita webhook ni servidor)
    - Procesa solo mensajes del chat_id configurado (seguridad)
    - Mantiene estado del último post generado para confirm/publish

Uso:
    python -m mikalia chat
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

import requests

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.telegram_listener")


def _markdown_to_telegram(text: str) -> str:
    """
    Convierte markdown de Claude a HTML de Telegram.

    Maneja: code blocks, inline code, bold, italic, headers, listas.
    Telegram soporta: <b>, <i>, <code>, <pre>, <a>.
    """
    # 1. Proteger code blocks (``` ... ```)
    code_blocks: list[str] = []

    def _save_code_block(match: re.Match) -> str:
        _lang = match.group(1) or ""  # noqa: F841 — preservar para uso futuro
        code = match.group(2).strip()
        code_blocks.append(f"<pre><code>{code}</code></pre>")
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    text = re.sub(r"```(\w*)\n?(.*?)```", _save_code_block, text, flags=re.DOTALL)

    # 2. Inline code (`...`)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # 3. Headers (## ... → bold)
    text = re.sub(r"^#{1,4}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 4. Bold (**...**)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # 5. Italic (*...*)  — solo si no es parte de lista
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", text)

    # 6. Links [text](url) → text (url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # 7. Bullet lists (- item → • item)
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    # 8. Restaurar code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", block)

    return text.strip()


class TelegramListener:
    """
    Escucha mensajes de Telegram y ejecuta comandos de Mikalia.

    Solo procesa mensajes del chat_id autorizado (el de Mikata-kun).
    Usa long polling para recibir updates sin necesidad de webhook.

    Args:
        bot_token: Token del bot de Telegram.
        chat_id: ID del chat autorizado.
        on_message: Callback que recibe (texto, responder_fn).
    """

    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        on_message: Any = None,
    ):
        self._bot_token = bot_token
        self._chat_id = str(chat_id)
        self._api_url = self.API_BASE.format(token=bot_token)
        self._on_message = on_message
        self._offset = 0
        self._running = False

    def send(self, text: str) -> bool:
        """Envía un mensaje al chat autorizado."""
        url = f"{self._api_url}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.json().get("ok", False)
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
            return False

    def send_and_edit(self, initial_text: str) -> int | None:
        """
        Envia un mensaje inicial y retorna su message_id para editarlo despues.

        Util para streaming: se envia un primer fragmento y luego se actualiza
        conforme llegan mas datos.

        Args:
            initial_text: Texto del mensaje inicial.

        Returns:
            message_id del mensaje enviado, o None si fallo.
        """
        url = f"{self._api_url}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": initial_text,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            if data.get("ok"):
                return data["result"]["message_id"]
            return None
        except Exception as e:
            logger.error(f"Error en send_and_edit: {e}")
            return None

    def edit_message(self, message_id: int, new_text: str) -> bool:
        """
        Edita un mensaje existente por su message_id.

        Args:
            message_id: ID del mensaje a editar.
            new_text: Nuevo texto del mensaje.

        Returns:
            True si la edicion fue exitosa.
        """
        url = f"{self._api_url}/editMessageText"
        payload = {
            "chat_id": self._chat_id,
            "message_id": message_id,
            "text": new_text,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.json().get("ok", False)
        except Exception as e:
            logger.error(f"Error editando mensaje: {e}")
            return False

    def send_typing(self) -> None:
        """Envia indicador de 'typing...' al chat."""
        url = f"{self._api_url}/sendChatAction"
        payload = {
            "chat_id": self._chat_id,
            "action": "typing",
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

    def listen(self, poll_interval: int = 1):
        """
        Inicia el loop de escucha con long polling.

        Args:
            poll_interval: Segundos entre polls (default 1).
        """
        self._running = True
        logger.info("Escuchando mensajes de Telegram...")

        while self._running:
            try:
                updates = self._get_updates(timeout=30)

                for update in updates:
                    self._process_update(update)

            except KeyboardInterrupt:
                self._running = False
                logger.info("Listener detenido por el usuario")
                break
            except Exception as e:
                logger.error(f"Error en listener: {e}")
                time.sleep(poll_interval)

    def stop(self):
        """Detiene el loop de escucha."""
        self._running = False

    def _get_updates(self, timeout: int = 30) -> list[dict]:
        """Obtiene nuevos mensajes via long polling."""
        url = f"{self._api_url}/getUpdates"
        params = {
            "offset": self._offset,
            "timeout": timeout,
            "allowed_updates": '["message"]',
        }

        try:
            resp = requests.get(url, params=params, timeout=timeout + 5)
            data = resp.json()

            if not data.get("ok"):
                return []

            results = data.get("result", [])

            # Actualizar offset para no recibir el mismo mensaje 2 veces
            if results:
                self._offset = results[-1]["update_id"] + 1

            return results

        except requests.Timeout:
            return []
        except Exception as e:
            logger.error(f"Error obteniendo updates: {e}")
            return []

    def send_voice(self, audio_path: str) -> bool:
        """Envia un archivo de audio como mensaje de voz."""
        url = f"{self._api_url}/sendVoice"
        try:
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    url,
                    data={"chat_id": self._chat_id},
                    files={"voice": f},
                    timeout=30,
                )
            return resp.json().get("ok", False)
        except Exception as e:
            logger.error(f"Error enviando voz: {e}")
            return False

    def _download_voice(self, file_id: str) -> str | None:
        """Descarga un voice message de Telegram y retorna path local."""
        try:
            # Obtener file_path del server
            url = f"{self._api_url}/getFile"
            resp = requests.get(url, params={"file_id": file_id}, timeout=10)
            data = resp.json()
            if not data.get("ok"):
                return None

            file_path = data["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self._bot_token}/{file_path}"

            # Descargar archivo
            voice_dir = Path("data/voice")
            voice_dir.mkdir(parents=True, exist_ok=True)
            local_path = voice_dir / f"telegram_{int(time.time())}.ogg"

            audio_resp = requests.get(download_url, timeout=30)
            local_path.write_bytes(audio_resp.content)

            return str(local_path)
        except Exception as e:
            logger.error(f"Error descargando voice: {e}")
            return None

    def _process_update(self, update: dict):
        """Procesa un update de Telegram (texto o voz)."""
        message = update.get("message")
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))

        # Solo procesar mensajes del chat autorizado
        if chat_id != self._chat_id:
            logger.warning(f"Mensaje ignorado de chat no autorizado: {chat_id}")
            return

        # Voice message
        voice = message.get("voice")
        if voice and self._on_message:
            file_id = voice.get("file_id", "")
            logger.info(f"Voice message recibido ({voice.get('duration', 0)}s)")
            audio_path = self._download_voice(file_id)
            if audio_path:
                self._on_message(audio_path, self.send, voice=True)
            else:
                self.send("No pude descargar el audio, intenta de nuevo~")
            return

        # Text message
        text = message.get("text", "").strip()
        if not text:
            return

        logger.info(f"Mensaje recibido: {text}")

        if self._on_message:
            self._on_message(text, self.send)


class MikaliaChatBot:
    """
    Lógica del chatbot de Mikalia.

    Interpreta mensajes de Mikata-kun y ejecuta acciones:
    - Genera posts
    - Muestra estado
    - Responde saludos

    Mantiene estado del último post generado para poder
    publicarlo con confirmación.
    """

    def __init__(self, config, client):
        self._config = config
        self._client = client
        self._last_post = None  # Último post generado (para confirmar)
        self._awaiting_confirm = False

    def handle_message(self, text: str, reply, voice: bool = False):
        """
        Procesa un mensaje y responde.

        Args:
            text: Texto del mensaje recibido.
            reply: Función para enviar respuesta.
        """
        text_lower = text.lower().strip()

        # Comandos de Telegram (/start, /help, /status)
        if text_lower.startswith("/start"):
            reply(
                "Hola Mikata-kun~ Soy Mikalia, tu agente de IA.\n\n"
                "Puedes pedirme cosas como:\n"
                "- <b>post [tema]</b> - Generar un post\n"
                "- <b>publica</b> - Publicar el ultimo post\n"
                "- <b>/status</b> - Ver mi estado\n"
                "- <b>/help</b> - Ver comandos\n\n"
                "<i>Stay curious~</i>"
            )
            return

        if text_lower.startswith("/help"):
            reply(
                "<b>Comandos de Mikalia:</b>\n\n"
                "<b>post</b> [tema] - Genera un post (preview)\n"
                "<b>publica</b> - Publica el ultimo post generado\n"
                "<b>cancela</b> - Cancela el post pendiente\n"
                "<b>/status</b> - Estado del bot\n"
                "<b>/help</b> - Esta ayuda\n\n"
                "Tambien puedes simplemente escribirme "
                "y respondo como Mikalia~"
            )
            return

        if text_lower.startswith("/status"):
            self._cmd_status(reply)
            return

        # Confirmar publicación
        if self._awaiting_confirm and text_lower in (
            "si", "sí", "yes", "publica", "dale", "ok", "publicalo", "publícalo"
        ):
            self._cmd_publish(reply)
            return

        if self._awaiting_confirm and text_lower in (
            "no", "cancela", "cancel", "nah", "nel"
        ):
            self._last_post = None
            self._awaiting_confirm = False
            reply("OK, post cancelado. Dime si quieres otro tema~")
            return

        # Comando: post <tema>
        if text_lower.startswith("post "):
            tema = text[5:].strip()
            if tema:
                self._cmd_generate_post(tema, reply)
                return

        # Saludos casuales
        saludos = ["hola", "hi", "hey", "holi", "ola", "hello", "buenas"]
        if text_lower in saludos:
            reply(
                "Hola Mikata-kun~ Como andamos?\n"
                "Dime si quieres que genere un post o algo mas~"
            )
            return

        # Cualquier otro texto: responder con Mikalia personality
        self._cmd_chat(text, reply)

    def _cmd_status(self, reply):
        """Muestra estado del bot."""
        has_pending = "Si" if self._last_post else "No"
        reply(
            "<b>Estado de Mikalia:</b>\n\n"
            f"Modelo: {self._config.mikalia.model}\n"
            f"Blog: {self._config.blog.repo_path or 'N/A'}\n"
            f"Telegram: Activo\n"
            f"Post pendiente: {has_pending}\n\n"
            "<i>Todo bien por aqui~</i>"
        )

    def _cmd_generate_post(self, tema: str, reply):
        """Genera un post y lo muestra como preview."""
        reply(f"Generando post sobre: <b>{tema}</b>\nDame un momento~")

        try:
            from mikalia.generation.post_generator import PostGenerator

            generator = PostGenerator(self._client, self._config)
            post = generator.generate_post(topic=tema)

            self._last_post = post
            self._awaiting_confirm = True

            # Mostrar preview
            preview = (
                f"<b>Post generado!</b>\n\n"
                f"<b>EN:</b> {post.metadata.title_en}\n"
                f"<b>ES:</b> {post.metadata.title_es}\n"
                f"<b>Tags:</b> {', '.join(post.metadata.tags)}\n"
                f"<b>Review:</b> {'Aprobado' if post.review_passed else 'Pendiente'}\n\n"
                f"<b>Preview (primeros 300 chars):</b>\n"
                f"<i>{post.content_en[:300]}...</i>\n\n"
                f"Quieres que lo publique? (si/no)"
            )
            reply(preview)

        except Exception as e:
            logger.error(f"Error generando post: {e}")
            reply(f"Error generando post: {e}")
            self._awaiting_confirm = False

    def _cmd_publish(self, reply):
        """Publica el último post generado."""
        if not self._last_post:
            reply("No hay post pendiente. Genera uno primero con: post [tema]")
            return

        reply("Publicando post... Un momento~")

        try:
            from mikalia.publishing.hugo_formatter import HugoFormatter
            from mikalia.publishing.git_ops import GitOperations

            formatter = HugoFormatter(self._config)
            formatted = formatter.format_post(self._last_post)

            git = GitOperations(self._config.blog.repo_path, self._config)
            git.sync_repo()
            commit_hash = git.publish_post(
                formatted.files,
                self._last_post.metadata.title_en,
            )

            blog_url = f"https://mikata-ai-lab.github.io/blog/{self._last_post.metadata.slug}/"

            reply(
                f"Post publicado!\n\n"
                f"<b>{self._last_post.metadata.title_en}</b>\n"
                f"Commit: <code>{commit_hash[:7]}</code>\n"
                f"URL: {blog_url}\n\n"
                f"<i>Stay curious~</i>"
            )

            self._last_post = None
            self._awaiting_confirm = False

        except Exception as e:
            logger.error(f"Error publicando: {e}")
            reply(f"Error publicando: {e}")

    def _cmd_chat(self, text: str, reply):
        """Responde como Mikalia usando Claude API."""
        try:
            respuesta = self._client.generate(
                user_prompt=text,
                temperature=0.7,
                max_tokens=500,
            )
            # Limpiar markdown que Telegram no soporta
            clean = respuesta.content.replace("**", "").replace("*", "")
            reply(clean)
        except Exception as e:
            reply(f"Perdon, tuve un error: {e}")


_TOOL_KEYWORDS = {
    "post", "blog", "commit", "push", "deploy", "pr", "review",
    "analiza", "analyze", "codigo", "code", "genera", "generate",
    "crea", "create", "escribe", "write", "ejecuta", "run",
    "busca", "search", "archivo", "file", "test", "docker",
    "brief", "goal", "fact", "skill", "tool", "haz", "hazme",
    "agrega", "add", "actualiza", "update", "borra", "delete",
    "imagen", "image", "email", "correo", "resumen", "summary",
    "pomodoro", "gasto", "expense", "habito", "habit",
}


class MikaliaCoreBot:
    """
    Chatbot que usa MikaliaAgent (Core) para responder.

    A diferencia de MikaliaChatBot (que es command-based),
    este usa el agent loop completo con memoria, tools,
    y self-improvement.

    Mensajes casuales se rutean a Haiku (barato, rapido).
    Mensajes que necesitan tools se rutean a Sonnet (completo).

    Comandos rapidos (no pasan por el agent loop):
        /start  — Saludo
        /help   — Ayuda
        /brief  — Daily brief rapido
        /goals  — Goals activos
        /facts  — Facts conocidos

    Todo lo demas pasa por el agent loop completo.

    Args:
        agent: MikaliaAgent ya inicializado.
        listener: TelegramListener para enviar typing indicator.
    """

    STREAM_EDIT_INTERVAL = 1.5  # Segundos entre ediciones del mensaje

    def __init__(self, agent, listener=None) -> None:
        from mikalia.core.agent import MikaliaAgent
        self._agent: MikaliaAgent = agent
        self._listener = listener
        self._session_id: str | None = self._resume_session()
        self._last_stream_sent: bool = False

    def shutdown(self) -> None:
        """Cierre limpio: finaliza la sesion en memoria."""
        if self._session_id:
            try:
                self._agent.memory.end_session(
                    self._session_id,
                    summary="Sesion cerrada por shutdown del bot.",
                )
                logger.info(f"Sesion {self._session_id[:8]}... cerrada limpiamente.")
            except Exception:
                pass

    @staticmethod
    def _classify_message(text: str) -> str:
        """Clasifica mensaje como 'casual' (Haiku) o 'tools' (Sonnet)."""
        lower = text.lower().strip()
        if any(kw in lower for kw in _TOOL_KEYWORDS):
            return "tools"
        if len(lower) > 150:
            return "tools"
        return "casual"

    def _transcribe_voice(self, audio_path: str) -> str | None:
        """Transcribe audio con SpeechToTextTool."""
        try:
            from mikalia.tools.voice import SpeechToTextTool
            stt = SpeechToTextTool()
            result = stt.execute(audio_path=audio_path)
            if result.success:
                return result.output
            logger.error(f"STT error: {result.error}")
            return None
        except Exception as e:
            logger.error(f"Error en transcripcion: {e}")
            return None

    def _send_voice_response(self, text: str) -> None:
        """Genera audio TTS y lo envia por Telegram."""
        try:
            from mikalia.tools.voice import TextToSpeechTool
            tts = TextToSpeechTool()
            result = tts.execute(text=text[:500])  # Limitar para TTS
            if result.success and self._listener:
                # El output contiene el path del MP3
                audio_path = result.output.strip()
                if Path(audio_path).exists():
                    self._listener.send_voice(audio_path)
                    return
            logger.warning("TTS fallo, respuesta solo texto")
        except Exception as e:
            logger.error(f"Error generando voz: {e}")

    def handle_message(self, text: str, reply, voice: bool = False):
        """Procesa un mensaje con el agente completo."""
        # Si es voice message, transcribir primero
        if voice:
            transcribed = self._transcribe_voice(text)  # text es audio_path
            if not transcribed:
                reply("No pude entender el audio, intenta de nuevo~")
                return
            logger.info(f"Transcripcion: {transcribed[:80]}...")
            text = transcribed

        text_lower = text.lower().strip()

        # Comandos rapidos (no usan API)
        if text_lower.startswith("/start"):
            reply(
                "Hola Mikata-kun~ Soy Mikalia Core v2.0\n\n"
                "Tengo memoria, 18 herramientas, y aprendo "
                "de cada conversacion.\n\n"
                "Comandos rapidos:\n"
                "/brief — Resumen del dia\n"
                "/goals — Ver goals activos\n"
                "/facts — Que se de ti\n"
                "/stats — Uso de tokens\n"
                "/help — Ayuda completa\n\n"
                "O simplemente escribeme lo que necesites~"
            )
            return

        if text_lower.startswith("/help"):
            reply(
                "<b>Mikalia Core v2.0</b>\n\n"
                "<b>Comandos rapidos:</b>\n"
                "/brief — Resumen diario\n"
                "/goals — Goals activos\n"
                "/facts — Mis recuerdos\n"
                "/stats — Uso de tokens\n\n"
                "<b>Puedo hacer:</b>\n"
                "• Investigar temas en la web\n"
                "• Crear y publicar posts en el blog\n"
                "• Revisar archivos y repos\n"
                "• Crear branches, commits, push y PRs en GitHub\n"
                "• Recordar cosas que me cuentes\n"
                "• Ejecutar comandos del sistema\n"
                "• Consultar y actualizar goals\n\n"
                "<i>Escribeme lo que necesites, yo uso "
                "mis herramientas automaticamente~</i>"
            )
            return

        if text_lower.startswith("/brief"):
            self._cmd_brief(reply)
            return

        if text_lower.startswith("/goals"):
            self._cmd_goals(reply)
            return

        if text_lower.startswith("/facts"):
            self._cmd_facts(reply)
            return

        if text_lower.startswith("/stats"):
            self._cmd_stats(reply)
            return

        # Clasificar: casual → Haiku sin tools, tools → Sonnet completo
        msg_type = self._classify_message(text)
        is_casual = msg_type == "casual"

        typing_stop = threading.Event()
        typing_thread = self._start_typing_loop(typing_stop)

        try:
            if is_casual:
                response = self._try_stream(text, reply)
                if response is None:
                    # Fallback a no-streaming
                    response = self._agent.process_message(
                        message=text,
                        channel="telegram",
                        session_id=self._session_id,
                        model_override=self._agent._config.mikalia.chat_model,
                        skip_tools=True,
                    )
            else:
                response = self._agent.process_message(
                    message=text,
                    channel="telegram",
                    session_id=self._session_id,
                )
            self._session_id = self._agent.session_id

            typing_stop.set()
            if typing_thread:
                typing_thread.join(timeout=1)

            # Responder con voz si el mensaje original era voz
            if voice:
                self._send_voice_response(response)
            # Si streaming ya envio la respuesta, no reenviar
            if not (is_casual and self._last_stream_sent):
                self._send_response(response, reply)

        except Exception as e:
            typing_stop.set()
            if typing_thread:
                typing_thread.join(timeout=1)
            logger.error(f"Error en MikaliaCoreBot: {e}")
            reply(f"Perdon, tuve un error procesando eso: {e}")

    def _try_stream(self, text: str, reply) -> str | None:
        """
        Intenta enviar la respuesta con streaming via edicion de mensaje.

        Envia un mensaje inicial con el primer fragmento y luego edita
        el mensaje cada ``STREAM_EDIT_INTERVAL`` segundos con el texto
        acumulado.

        Args:
            text: Mensaje del usuario.
            reply: Funcion para enviar respuestas (fallback).

        Returns:
            Texto completo de la respuesta si streaming funciono,
            o None si fallo (para que el caller haga fallback).
        """
        self._last_stream_sent = False

        if not self._listener:
            return None

        try:
            gen = self._agent.process_message_stream(
                message=text,
                channel="telegram",
                session_id=self._session_id,
                model_override=self._agent._config.mikalia.chat_model,
            )

            accumulated = ""
            message_id: int | None = None
            last_edit = 0.0

            for chunk in gen:
                accumulated += chunk

                now = time.time()

                # Enviar mensaje inicial con el primer fragmento
                if message_id is None and len(accumulated) >= 10:
                    clean = _markdown_to_telegram(accumulated)
                    message_id = self._listener.send_and_edit(clean)
                    last_edit = now
                    continue

                # Editar cada STREAM_EDIT_INTERVAL segundos
                if message_id is not None and (now - last_edit) >= self.STREAM_EDIT_INTERVAL:
                    clean = _markdown_to_telegram(accumulated)
                    self._listener.edit_message(message_id, clean)
                    last_edit = now

            # Edicion final con el texto completo
            if message_id is not None:
                clean = _markdown_to_telegram(accumulated)
                self._listener.edit_message(message_id, clean)
                self._last_stream_sent = True
            elif accumulated:
                # Si nunca se envio el mensaje inicial (texto muy corto)
                clean = _markdown_to_telegram(accumulated)
                reply(clean)
                self._last_stream_sent = True

            self._session_id = self._agent.session_id
            return accumulated

        except Exception as e:
            logger.warning(f"Streaming fallo, usando fallback: {e}")
            return None

    def _resume_session(self) -> str | None:
        """Intenta retomar la ultima sesion de Telegram."""
        try:
            last = self._agent.memory.get_last_session("telegram", max_age_hours=6)
            if last:
                logger.info(f"Retomando sesion anterior: {last['id'][:8]}...")
                return last["id"]
        except Exception:
            pass
        return None

    def _start_typing_loop(self, stop_event: threading.Event) -> threading.Thread | None:
        """Inicia un thread que envia typing cada 4 seg hasta que stop_event se active."""
        if not self._listener:
            return None

        def _loop():
            while not stop_event.is_set():
                self._listener.send_typing()
                stop_event.wait(timeout=4)

        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        return t

    def _send_response(self, response: str, reply):
        """Envia respuesta formateada, con chunks si es necesario."""
        clean = _markdown_to_telegram(response)

        if len(clean) > 4000:
            for i in range(0, len(clean), 4000):
                reply(clean[i:i + 4000])
        else:
            reply(clean)

    def _cmd_brief(self, reply):
        """Genera daily brief rapido sin pasar por el agent loop."""
        if self._listener:
            self._listener.send_typing()
        try:
            from mikalia.tools.daily_brief import DailyBriefTool
            tool = DailyBriefTool(self._agent.memory)
            result = tool.execute(format="telegram")
            reply(result.output if result.success else f"Error: {result.error}")
        except Exception as e:
            reply(f"Error generando brief: {e}")

    def _cmd_goals(self, reply):
        """Muestra goals activos."""
        try:
            goals = self._agent.memory.get_active_goals()
            if not goals:
                reply("No hay goals activos.")
                return

            lines = ["<b>Goals activos:</b>\n"]
            for g in goals:
                bar = self._progress_bar(g["progress"])
                lines.append(
                    f"<b>#{g['id']}</b> [{g.get('priority', 'medium').upper()}] "
                    f"{g['project']}\n"
                    f"  {g['title']}\n"
                    f"  {bar} {g['progress']}%\n"
                )
            reply("\n".join(lines))
        except Exception as e:
            reply(f"Error listando goals: {e}")

    def _cmd_facts(self, reply):
        """Muestra facts conocidos."""
        try:
            facts = self._agent.memory.get_facts(active_only=True)
            if not facts:
                reply("No tengo facts guardados aun.")
                return

            lines = [f"<b>Recuerdo {len(facts)} cosas:</b>\n"]
            for f in facts[:15]:
                lines.append(
                    f"[{f['category']}] <b>{f['subject']}</b>: "
                    f"{f['fact'][:80]}"
                )
            if len(facts) > 15:
                lines.append(f"\n<i>... y {len(facts) - 15} mas</i>")
            reply("\n".join(lines))
        except Exception as e:
            reply(f"Error listando facts: {e}")

    @staticmethod
    def _estimate_cost(tokens: int) -> float:
        """Estima costo USD basado en tokens (promedio $8/1M tokens)."""
        return tokens * 8 / 1_000_000

    def _cmd_stats(self, reply):
        """Muestra uso de tokens, costos y estadisticas."""
        try:
            mem = self._agent.memory

            # Stats de sesion actual
            session_stats = {"total_messages": 0, "total_tokens": 0}
            if self._session_id:
                session_stats = mem.get_session_stats(self._session_id)

            # Stats por periodo
            daily = mem.get_token_usage(hours=24)
            weekly = mem.get_token_usage(hours=168)
            monthly = mem.get_token_usage(hours=720)

            cost_daily = self._estimate_cost(daily["total_tokens"])
            cost_weekly = self._estimate_cost(weekly["total_tokens"])
            cost_monthly = self._estimate_cost(monthly["total_tokens"])

            lines = [
                "<b>Estadisticas de uso</b>\n",
                "<b>Sesion actual:</b>",
                f"  Mensajes: {session_stats['total_messages']}",
                f"  Tokens: {session_stats['total_tokens']:,}",
                "",
                "<b>Ultimas 24h:</b>",
                f"  Sesiones: {daily['sessions']}",
                f"  Mensajes: {daily['total_messages']}",
                f"  Tokens: {daily['total_tokens']:,}",
                f"  Costo: ~${cost_daily:.2f} USD",
                "",
                "<b>Ultimos 7 dias:</b>",
                f"  Sesiones: {weekly['sessions']}",
                f"  Tokens: {weekly['total_tokens']:,}",
                f"  Costo: ~${cost_weekly:.2f} USD",
                "",
                "<b>Ultimos 30 dias:</b>",
                f"  Sesiones: {monthly['sessions']}",
                f"  Tokens: {monthly['total_tokens']:,}",
                f"  Costo: ~${cost_monthly:.2f} USD",
            ]
            reply("\n".join(lines))
        except Exception as e:
            reply(f"Error obteniendo stats: {e}")

    @staticmethod
    def _progress_bar(progress: int, width: int = 10) -> str:
        filled = int(width * progress / 100)
        return "[" + "#" * filled + "." * (width - filled) + "]"
