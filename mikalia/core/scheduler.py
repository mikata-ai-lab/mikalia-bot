"""
scheduler.py — Mini-cron para Mikalia Core.

Ejecuta jobs programados en un thread daemon. Lee jobs de la tabla
scheduled_jobs (con cron expressions) y los ejecuta a la hora correcta.

Los resultados se envian por Telegram.

Uso:
    from mikalia.core.scheduler import MikaliaScheduler
    scheduler = MikaliaScheduler(memory, send_fn=listener.send)
    scheduler.start()
    ...
    scheduler.stop()
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Callable

from croniter import croniter

from mikalia.core.memory import MemoryManager
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.core.scheduler")


class MikaliaScheduler:
    """
    Scheduler basado en cron expressions para Mikalia.

    Lee jobs de scheduled_jobs, calcula el proximo run,
    y los ejecuta en un thread daemon.

    Args:
        memory: MemoryManager para leer jobs.
        send_fn: Funcion para enviar mensajes (telegram send).
        check_interval: Segundos entre verificaciones (default 60).
    """

    def __init__(
        self,
        memory: MemoryManager,
        send_fn: Callable[[str], bool] | None = None,
        check_interval: int = 60,
    ) -> None:
        self._memory = memory
        self._send_fn = send_fn
        self._check_interval = check_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._action_handlers: dict[str, Callable] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Registra handlers para las acciones conocidas."""
        self._action_handlers = {
            "daily-brief": self._handle_daily_brief,
            "health-reminder": self._handle_health_reminder,
            "weekly-review": self._handle_weekly_review,
        }

    def register_handler(self, skill_name: str, handler: Callable) -> None:
        """Registra un handler custom para un skill."""
        self._action_handlers[skill_name] = handler

    def start(self) -> None:
        """Inicia el scheduler en un thread daemon."""
        if self._thread and self._thread.is_alive():
            logger.warning("Scheduler ya esta corriendo.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="mikalia-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("Scheduler iniciado.")

    def stop(self) -> None:
        """Detiene el scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler detenido.")

    @property
    def is_running(self) -> bool:
        """True si el scheduler esta corriendo."""
        return self._thread is not None and self._thread.is_alive()

    def _run_loop(self) -> None:
        """Loop principal del scheduler."""
        logger.info(
            f"Scheduler loop iniciado. Verificando cada "
            f"{self._check_interval}s."
        )

        while not self._stop_event.is_set():
            try:
                self._check_and_execute()
            except Exception as e:
                logger.error(f"Error en scheduler loop: {e}")

            self._stop_event.wait(timeout=self._check_interval)

    def _check_and_execute(self) -> None:
        """Verifica si algun job debe ejecutarse ahora."""
        jobs = self._memory.get_scheduled_jobs(enabled_only=True)
        now = datetime.now()

        for job in jobs:
            try:
                if self._should_run(job, now):
                    logger.info(f"Ejecutando job: {job['name']}")
                    self._execute_job(job)
            except Exception as e:
                logger.error(f"Error procesando job '{job['name']}': {e}")

    def _should_run(self, job: dict, now: datetime) -> bool:
        """
        Determina si un job debe ejecutarse ahora.

        Logica:
        1. Si last_run_at existe, next_run = croniter(cron, last_run).next()
        2. Si last_run_at es None, verificar si ahora esta dentro de la ventana
        """
        cron_expr = job["cron_expression"]
        last_run = job.get("last_run_at")

        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
            except (ValueError, TypeError):
                last_dt = datetime.min
            cron = croniter(cron_expr, last_dt)
            next_run = cron.get_next(datetime)
            return now >= next_run
        else:
            # Nunca se ha ejecutado: verificar si ahora cae en la ventana
            from_time = now.replace(second=0, microsecond=0)
            from_time = from_time.replace(
                minute=max(0, from_time.minute - 2)
            )
            cron = croniter(cron_expr, from_time)
            next_run = cron.get_next(datetime)
            return now >= next_run

    def _execute_job(self, job: dict) -> None:
        """Ejecuta un job y actualiza last_run_at."""
        action = json.loads(job["action"])
        skill_name = action.get("skill", "")
        params = action.get("params", {})

        handler = self._action_handlers.get(skill_name)
        if handler:
            try:
                result = handler(params)
                if result and self._send_fn:
                    self._send_fn(result)
                logger.success(f"Job '{job['name']}' ejecutado OK.")
            except Exception as e:
                error_msg = f"Error ejecutando job '{job['name']}': {e}"
                logger.error(error_msg)
                if self._send_fn:
                    self._send_fn(f"[Scheduler] {error_msg}")
        else:
            logger.warning(
                f"No hay handler para skill '{skill_name}' "
                f"(job: {job['name']})"
            )

        # Actualizar last_run y calcular next_run
        cron = croniter(job["cron_expression"], datetime.now())
        next_run = cron.get_next(datetime)
        self._memory.update_job_last_run(
            job["id"],
            next_run_at=next_run.isoformat(),
        )

    # ================================================================
    # Built-in action handlers
    # ================================================================

    def _handle_daily_brief(self, params: dict) -> str | None:
        """Genera y retorna el daily brief."""
        try:
            from mikalia.tools.daily_brief import DailyBriefTool
            tool = DailyBriefTool(self._memory)
            result = tool.execute(format="telegram")
            return result.output if result.success else f"Error: {result.error}"
        except Exception as e:
            logger.error(f"Error en daily_brief: {e}")
            return f"Error generando brief: {e}"

    def _handle_health_reminder(self, params: dict) -> str | None:
        """Envia recordatorio de salud."""
        return (
            "<b>Recordatorio de salud</b>\n\n"
            "Mikata-kun, son las 10 PM.\n"
            "Recuerda el pacto: dormir antes de las 11.\n\n"
            "Cierra todo, deja la compu, y descansa.\n"
            "Tu salud es lo primero~\n\n"
            "<i>Buenas noches.</i>"
        )

    def _handle_weekly_review(self, params: dict) -> str | None:
        """Genera resumen semanal de progreso."""
        try:
            goals = self._memory.get_active_goals()
            if not goals:
                return "<b>Review semanal:</b>\nNo hay goals activos."

            lines = ["<b>Review semanal de progreso</b>\n"]
            for g in goals:
                priority = g.get("priority", "medium").upper()
                lines.append(
                    f"[{priority}] <b>{g['project']}</b>: {g['title']}\n"
                    f"  Progreso: {g['progress']}%"
                )

            usage = self._memory.get_token_usage(hours=168)  # 7 dias
            lines.append(
                f"\n<b>Uso semanal:</b>\n"
                f"  Sesiones: {usage['sessions']}\n"
                f"  Mensajes: {usage['total_messages']}\n"
                f"  Tokens: {usage['total_tokens']:,}"
            )

            lines.append("\n<i>Buen domingo, Mikata-kun~</i>")
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error en weekly_review: {e}")
            return f"Error generando review: {e}"
