"""
api.py — Servidor FastAPI de Mikalia.

Expone endpoints HTTP para monitoreo, stats y webhooks.
Es el "sistema nervioso" que permite a Mikalia escuchar del mundo.

Endpoints:
    GET  /             — Info basica de Mikalia
    GET  /health       — Health check para monitoreo VPS
    GET  /stats        — Token usage, conversations, facts
    GET  /goals        — Goals activos con progreso
    GET  /jobs         — Scheduled jobs y estado
    POST /webhook/github    — Webhook para eventos de GitHub
    GET  /webhook/whatsapp  — Verificacion de webhook (Meta)
    POST /webhook/whatsapp  — Mensajes entrantes de WhatsApp

Uso:
    python -m mikalia serve
    python -m mikalia serve --port 8080
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from mikalia.core.memory import MemoryManager
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.api")

# ================================================================
# App factory
# ================================================================

_start_time: float = 0.0


def create_app(
    memory: MemoryManager | None = None,
    db_path: str | None = None,
    whatsapp_listener: Any = None,
    twilio_listener: Any = None,
) -> FastAPI:
    """
    Crea la app FastAPI de Mikalia.

    Args:
        memory: MemoryManager existente (reutiliza conexion).
        db_path: Ruta a la DB si no se pasa memory.

    Returns:
        FastAPI app lista para servir.
    """
    global _start_time
    _start_time = time.time()

    app = FastAPI(
        title="Mikalia API",
        description="Sistema nervioso de Mikalia — monitoreo, stats y webhooks",
        version="1.0.0",
    )

    # Resolver memory
    if memory is None:
        schema_path = Path(__file__).parent / "core" / "schema.sql"
        resolved_db = db_path or os.environ.get(
            "MIKALIA_DB_PATH", "data/mikalia.db"
        )
        memory = MemoryManager(resolved_db, str(schema_path))

    app.state.memory = memory
    app.state.whatsapp_listener = whatsapp_listener
    app.state.twilio_listener = twilio_listener

    _register_routes(app)

    return app


# ================================================================
# Routes
# ================================================================


def _register_routes(app: FastAPI) -> None:
    """Registra todos los endpoints."""

    @app.get("/")
    async def root():
        """Info basica de Mikalia."""
        return {
            "name": "Mikalia",
            "version": "2.0",
            "status": "alive",
            "uptime_seconds": int(time.time() - _start_time),
            "message": "Stay curious~ ✨",
        }

    @app.get("/health")
    async def health():
        """
        Health check para monitoreo en VPS.

        Verifica: DB conectada, uptime, timestamp.
        Retorna 200 si todo OK, 503 si algo falla.
        """
        checks = {
            "database": False,
            "uptime_seconds": int(time.time() - _start_time),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            memory: MemoryManager = app.state.memory
            # Verificar DB haciendo una query simple
            facts = memory.get_facts(active_only=True)
            checks["database"] = True
            checks["facts_count"] = len(facts)
        except Exception as e:
            checks["database_error"] = str(e)

        all_ok = checks["database"]
        status_code = 200 if all_ok else 503

        return JSONResponse(
            content={
                "status": "healthy" if all_ok else "degraded",
                "checks": checks,
            },
            status_code=status_code,
        )

    @app.get("/stats")
    async def stats():
        """
        Estadisticas de uso de Mikalia.

        Token usage (24h y 7d), conversaciones, facts, goals.
        """
        memory: MemoryManager = app.state.memory

        usage_24h = memory.get_token_usage(hours=24)
        usage_7d = memory.get_token_usage(hours=168)

        try:
            facts = memory.get_facts(active_only=True)
            facts_count = len(facts)
        except Exception:
            facts_count = 0

        try:
            goals = memory.get_active_goals()
            goals_active = len(goals)
        except Exception:
            goals_active = 0

        try:
            lessons = memory.get_facts(category="lesson", active_only=True)
            lessons_count = len(lessons)
        except Exception:
            lessons_count = 0

        return {
            "token_usage": {
                "last_24h": {
                    "tokens": usage_24h["total_tokens"],
                    "messages": usage_24h["total_messages"],
                    "sessions": usage_24h["sessions"],
                },
                "last_7d": {
                    "tokens": usage_7d["total_tokens"],
                    "messages": usage_7d["total_messages"],
                    "sessions": usage_7d["sessions"],
                },
            },
            "memory": {
                "facts": facts_count,
                "lessons": lessons_count,
                "goals_active": goals_active,
            },
            "uptime_seconds": int(time.time() - _start_time),
        }

    @app.get("/goals")
    async def goals():
        """Lista goals activos con progreso."""
        memory: MemoryManager = app.state.memory

        active_goals = memory.get_active_goals()
        return {
            "goals": [
                {
                    "project": g["project"],
                    "title": g["title"],
                    "status": g["status"],
                    "priority": g["priority"],
                    "progress": g["progress"],
                }
                for g in active_goals
            ],
            "total": len(active_goals),
        }

    @app.get("/jobs")
    async def jobs():
        """Lista scheduled jobs y su estado."""
        memory: MemoryManager = app.state.memory

        all_jobs = memory.get_scheduled_jobs(enabled_only=False)
        return {
            "jobs": [
                {
                    "name": j["name"],
                    "description": j["description"],
                    "cron": j["cron_expression"],
                    "enabled": bool(j["is_enabled"]),
                    "last_run": j["last_run_at"],
                    "next_run": j["next_run_at"],
                }
                for j in all_jobs
            ],
            "total": len(all_jobs),
        }

    @app.post("/webhook/github")
    async def webhook_github(request: Request):
        """
        Webhook para eventos de GitHub.

        Placeholder — sera expandido para recibir eventos
        de PRs, pushes, CI failures, etc.
        """
        try:
            await request.json()  # Consumir body del webhook
            event_type = request.headers.get("X-GitHub-Event", "unknown")

            logger.info(f"GitHub webhook: {event_type}")

            # TODO: Procesar eventos y notificar por Telegram
            return {
                "received": True,
                "event": event_type,
                "message": "Webhook received. Processing not yet implemented.",
            }
        except Exception as e:
            return JSONResponse(
                content={"error": str(e)},
                status_code=400,
            )

    # ============================================================
    # WhatsApp Webhook
    # ============================================================

    @app.get("/webhook/whatsapp")
    async def webhook_whatsapp_verify(
        request: Request,
    ):
        """
        Verificacion del webhook de WhatsApp (Meta).

        Meta envia un GET con hub.mode, hub.verify_token y hub.challenge.
        Debemos responder con el challenge si el token es correcto.
        """
        mode = request.query_params.get("hub.mode", "")
        token = request.query_params.get("hub.verify_token", "")
        challenge = request.query_params.get("hub.challenge", "")

        listener = app.state.whatsapp_listener
        if listener is None:
            return JSONResponse(
                content={"error": "WhatsApp not configured"},
                status_code=503,
            )

        result = listener.handle_webhook_verify(mode, token, challenge)
        if result is not None:
            return PlainTextResponse(content=result)

        return JSONResponse(
            content={"error": "Verification failed"},
            status_code=403,
        )

    @app.post("/webhook/whatsapp")
    async def webhook_whatsapp_message(request: Request):
        """
        Recibe mensajes entrantes de WhatsApp.

        Meta envia un POST con el payload del mensaje.
        Lo procesamos y respondemos via el WhatsAppListener.
        """
        listener = app.state.whatsapp_listener
        if listener is None:
            return JSONResponse(
                content={"error": "WhatsApp not configured"},
                status_code=503,
            )

        try:
            payload = await request.json()
            result = listener.handle_webhook_message(payload)
            logger.info(f"WhatsApp webhook: {result}")
            return result
        except Exception as e:
            logger.error(f"Error en webhook WhatsApp: {e}")
            return JSONResponse(
                content={"error": str(e)},
                status_code=400,
            )

    # ============================================================
    # Twilio WhatsApp Webhook
    # ============================================================

    @app.post("/webhook/twilio")
    async def webhook_twilio(request: Request):
        """
        Recibe mensajes de WhatsApp via Twilio.

        Twilio envia POST form-encoded (no JSON).
        Campos: From, To, Body, MessageSid, NumMedia, etc.
        """
        listener = app.state.twilio_listener
        if listener is None:
            return JSONResponse(
                content={"error": "Twilio not configured"},
                status_code=503,
            )

        try:
            form = await request.form()
            form_data = dict(form)
            result = listener.handle_webhook(form_data)
            logger.info(f"Twilio webhook: {result}")

            # Twilio espera 200 OK con TwiML vacio
            # (respondemos via API, no via TwiML)
            return PlainTextResponse(
                content="<Response></Response>",
                media_type="application/xml",
            )
        except Exception as e:
            logger.error(f"Error en webhook Twilio: {e}")
            return JSONResponse(
                content={"error": str(e)},
                status_code=400,
            )
