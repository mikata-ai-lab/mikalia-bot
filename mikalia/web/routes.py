"""
routes.py — Endpoints del web chat de Mikalia.

Smart routing: casual → Haiku streaming, tools → Sonnet con 44 herramientas.
Misma logica que Telegram pero con SSE en vez de editMessageText.

Endpoints:
    GET  /chat              — Pagina HTML del chat
    POST /api/chat          — Chat sincrono (fallback)
    POST /api/chat/stream   — Chat SSE con routing inteligente
    GET  /api/chat/history  — Historial de conversacion
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from mikalia.notifications.telegram_listener import _TOOL_KEYWORDS
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.web")

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


def _classify_message(text: str) -> str:
    """Clasifica mensaje como 'casual' (Haiku streaming) o 'tools' (Sonnet)."""
    lower = text.lower().strip()
    if any(kw in lower for kw in _TOOL_KEYWORDS):
        return "tools"
    if len(lower) > 150:
        return "tools"
    return "casual"


@router.get("/chat", response_class=HTMLResponse)
async def chat_page():
    """Sirve la pagina HTML del chat."""
    html_path = TEMPLATES_DIR / "chat.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@router.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    """SSE con routing inteligente — casual streaming o tools completo."""
    agent = request.app.state.agent

    if agent is None:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'Agent not initialized'})}\n\n"]),
            media_type="text/event-stream",
        )

    msg_type = _classify_message(body.message)

    def event_generator():
        session_id = body.session_id

        if not session_id:
            session_id = agent.memory.create_session("web")

        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"

        try:
            if msg_type == "casual":
                # Casual → Haiku streaming (sin tools)
                try:
                    chat_model = getattr(
                        agent._config.mikalia, "chat_model",
                        "claude-haiku-4-5-20251001",
                    )
                    for chunk in agent.process_message_stream(
                        message=body.message,
                        channel="web",
                        session_id=session_id,
                        model_override=chat_model,
                    ):
                        yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
                except Exception as stream_err:
                    logger.warning(f"Stream fallback: {stream_err}")
                    # Fallback: sync con Haiku sin tools
                    response = agent.process_message(
                        message=body.message,
                        channel="web",
                        session_id=session_id,
                        model_override=chat_model,
                        skip_tools=True,
                    )
                    yield f"data: {json.dumps({'type': 'chunk', 'text': response})}\n\n"
            else:
                # Tools → Sonnet con 44 herramientas (sin streaming)
                response = agent.process_message(
                    message=body.message,
                    channel="web",
                    session_id=session_id,
                )
                yield f"data: {json.dumps({'type': 'chunk', 'text': response})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error(f"Error en chat: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/chat")
async def chat_sync(body: ChatRequest, request: Request):
    """Chat sincrono — fallback sin streaming."""
    agent = request.app.state.agent

    if agent is None:
        return {"error": "Agent not initialized", "response": "", "session_id": None}

    session_id = body.session_id

    if not session_id:
        session_id = agent.memory.create_session("web")

    response = agent.process_message(
        message=body.message,
        channel="web",
        session_id=session_id,
    )

    return {
        "response": response,
        "session_id": session_id,
    }


@router.get("/api/chat/history")
async def chat_history(session_id: str, request: Request):
    """Historial de conversacion de una sesion."""
    agent = request.app.state.agent

    if agent is None:
        return {"messages": [], "session_id": session_id}

    messages = agent.memory.get_session_messages(session_id)

    return {
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ],
        "session_id": session_id,
    }
