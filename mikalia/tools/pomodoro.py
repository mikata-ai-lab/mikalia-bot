"""
pomodoro.py — Timer de productividad para Mikalia.

Implementa la tecnica Pomodoro:
- 25 min de trabajo enfocado
- 5 min de descanso
- Cada 4 pomodoros: 15 min de descanso largo

Almacena sesiones completadas en memoria.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.pomodoro")

# Estado global del timer
_active_timer: dict[str, Any] | None = None
_timer_thread: threading.Thread | None = None
_timer_stop: threading.Event = threading.Event()


class PomodoroTool(BaseTool):
    """Timer Pomodoro con notificaciones."""

    def __init__(self, notify_fn=None) -> None:
        self._notify = notify_fn
        self._completed_today = 0

    @property
    def name(self) -> str:
        return "pomodoro"

    @property
    def description(self) -> str:
        return (
            "Pomodoro productivity timer. Actions: "
            "start (begin a focus session), "
            "stop (cancel current timer), "
            "status (check timer and stats). "
            "Default: 25min work, 5min break. "
            "Notifies when timer completes."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: start, stop, or status",
                    "enum": ["start", "stop", "status"],
                },
                "minutes": {
                    "type": "integer",
                    "description": "Duration in minutes (default: 25)",
                },
                "label": {
                    "type": "string",
                    "description": "Label for this session (e.g., 'coding', 'writing')",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        minutes: int = 25,
        label: str = "focus",
        **_: Any,
    ) -> ToolResult:
        global _active_timer, _timer_thread

        if action == "start":
            return self._start(minutes, label)
        elif action == "stop":
            return self._stop()
        elif action == "status":
            return self._status()
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _start(self, minutes: int, label: str) -> ToolResult:
        global _active_timer, _timer_thread

        if _active_timer is not None:
            elapsed = int(time.time() - _active_timer["start_time"])
            remaining = _active_timer["duration"] - elapsed
            return ToolResult(
                success=False,
                error=(
                    f"Ya hay un timer activo: {_active_timer['label']} "
                    f"({remaining // 60}m {remaining % 60}s restantes). "
                    f"Usa action='stop' para cancelarlo."
                ),
            )

        minutes = max(1, min(minutes, 120))
        duration = minutes * 60

        _timer_stop.clear()
        _active_timer = {
            "label": label,
            "duration": duration,
            "start_time": time.time(),
            "minutes": minutes,
        }

        # Thread que espera y notifica
        def _wait():
            global _active_timer
            finished = _timer_stop.wait(timeout=duration)
            if not finished:
                # Timer completo (no fue cancelado)
                self._completed_today += 1
                msg = (
                    f"Pomodoro completado: {label} ({minutes}min)\n"
                    f"Sesiones hoy: {self._completed_today}\n"
                    f"Toma un descanso de 5 minutos~"
                )
                logger.success(msg)
                if self._notify:
                    self._notify(msg)
            _active_timer = None

        _timer_thread = threading.Thread(target=_wait, daemon=True)
        _timer_thread.start()

        logger.info(f"Pomodoro iniciado: {label} ({minutes}min)")
        return ToolResult(
            success=True,
            output=(
                f"Pomodoro iniciado!\n"
                f"Label: {label}\n"
                f"Duracion: {minutes} minutos\n"
                f"Te aviso cuando termine~"
            ),
        )

    def _stop(self) -> ToolResult:
        global _active_timer

        if _active_timer is None:
            return ToolResult(
                success=False,
                error="No hay timer activo.",
            )

        label = _active_timer["label"]
        elapsed = int(time.time() - _active_timer["start_time"])
        _timer_stop.set()

        return ToolResult(
            success=True,
            output=(
                f"Pomodoro cancelado: {label}\n"
                f"Tiempo transcurrido: {elapsed // 60}m {elapsed % 60}s"
            ),
        )

    def _status(self) -> ToolResult:
        if _active_timer is None:
            return ToolResult(
                success=True,
                output=(
                    f"No hay timer activo.\n"
                    f"Pomodoros completados hoy: {self._completed_today}"
                ),
            )

        elapsed = int(time.time() - _active_timer["start_time"])
        remaining = _active_timer["duration"] - elapsed
        remaining = max(0, remaining)

        return ToolResult(
            success=True,
            output=(
                f"Timer activo: {_active_timer['label']}\n"
                f"Duracion: {_active_timer['minutes']}min\n"
                f"Transcurrido: {elapsed // 60}m {elapsed % 60}s\n"
                f"Restante: {remaining // 60}m {remaining % 60}s\n"
                f"Pomodoros completados hoy: {self._completed_today}"
            ),
        )
