"""
test_scheduler.py — Tests para el scheduler de Mikalia.

Verifica:
- Lectura de jobs de la DB
- Evaluacion de cron expressions
- Ejecucion de handlers
- Thread management
"""

from __future__ import annotations

import time

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from mikalia.core.memory import MemoryManager
from mikalia.core.scheduler import MikaliaScheduler


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    db_path = tmp_path / "test_scheduler.db"
    return MemoryManager(str(db_path), str(SCHEMA_PATH))


@pytest.fixture
def scheduler(memory):
    send_fn = MagicMock(return_value=True)
    sched = MikaliaScheduler(
        memory=memory,
        send_fn=send_fn,
        check_interval=1,
    )
    return sched


# ================================================================
# Scheduled Jobs en memoria
# ================================================================

class TestScheduledJobsMemory:
    def test_seed_jobs_loaded(self, memory):
        """Los seed jobs del schema.sql estan presentes."""
        jobs = memory.get_scheduled_jobs()
        assert len(jobs) == 4
        names = [j["name"] for j in jobs]
        assert "daily_brief_weekday" in names
        assert "health_evening_check" in names
        assert "weekly_review" in names

    def test_update_last_run(self, memory):
        """update_job_last_run actualiza el timestamp."""
        jobs = memory.get_scheduled_jobs()
        job = jobs[0]
        assert job["last_run_at"] is None

        memory.update_job_last_run(job["id"], next_run_at="2026-02-20T07:00:00")

        updated = memory.get_scheduled_jobs()
        updated_job = next(j for j in updated if j["id"] == job["id"])
        assert updated_job["last_run_at"] is not None
        assert updated_job["next_run_at"] == "2026-02-20T07:00:00"

    def test_get_all_jobs_including_disabled(self, memory):
        """enabled_only=False retorna todos los jobs."""
        all_jobs = memory.get_scheduled_jobs(enabled_only=False)
        enabled_jobs = memory.get_scheduled_jobs(enabled_only=True)
        assert len(all_jobs) >= len(enabled_jobs)


# ================================================================
# Should Run logic
# ================================================================

class TestShouldRun:
    def test_never_run_job_matches_now(self, scheduler):
        """Un job que nunca se ejecuto se ejecuta si la hora coincide."""
        now = datetime.now()
        job = {
            "cron_expression": f"{now.minute} {now.hour} * * *",
            "last_run_at": None,
        }
        assert scheduler._should_run(job, now) is True

    def test_recently_run_job_skipped(self, scheduler):
        """Un job que ya corrio recientemente no se ejecuta de nuevo."""
        now = datetime.now()
        job = {
            "cron_expression": "0 7 * * *",
            "last_run_at": now.isoformat(),
        }
        assert scheduler._should_run(job, now) is False

    def test_old_run_allows_execution(self, scheduler):
        """Un job cuyo last_run es viejo se ejecuta."""
        job = {
            "cron_expression": "* * * * *",  # Cada minuto
            "last_run_at": "2020-01-01T00:00:00",
        }
        assert scheduler._should_run(job, datetime.now()) is True


# ================================================================
# Handlers
# ================================================================

class TestHandlers:
    def test_daily_brief_handler(self, scheduler):
        """Handler de daily brief retorna texto."""
        result = scheduler._handle_daily_brief({})
        assert result is not None
        assert isinstance(result, str)

    def test_health_reminder_handler(self, scheduler):
        """Handler de health reminder retorna mensaje."""
        result = scheduler._handle_health_reminder({})
        assert "salud" in result.lower()
        assert "dormir" in result.lower()

    def test_weekly_review_handler(self, scheduler):
        """Handler de weekly review retorna texto."""
        result = scheduler._handle_weekly_review({})
        assert result is not None
        assert "review" in result.lower() or "Review" in result


# ================================================================
# Thread management
# ================================================================

class TestThreadManagement:
    def test_start_and_stop(self, scheduler):
        """Scheduler inicia y se detiene correctamente."""
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()
        time.sleep(0.5)
        assert not scheduler.is_running

    def test_double_start_no_crash(self, scheduler):
        """Iniciar dos veces no crea threads duplicados."""
        scheduler.start()
        scheduler.start()
        scheduler.stop()

    def test_register_custom_handler(self, scheduler):
        """Se pueden registrar handlers custom."""
        handler = MagicMock(return_value="custom result")
        scheduler.register_handler("custom-skill", handler)
        assert "custom-skill" in scheduler._action_handlers
