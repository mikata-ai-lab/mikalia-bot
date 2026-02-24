"""
test_pomodoro.py — Tests para PomodoroTool.

Verifica:
- Iniciar timer
- Iniciar cuando ya hay uno activo
- Detener timer
- Detener sin timer activo
- Status sin timer
- Status con timer activo
- Accion desconocida
- Definicion Claude correcta

IMPORTANTE: Se resetea el estado global del modulo antes de cada test.
"""

from __future__ import annotations

import time
import pytest
from unittest.mock import patch

import mikalia.tools.pomodoro as pomodoro_module
from mikalia.tools.pomodoro import PomodoroTool


# ================================================================
# PomodoroTool
# ================================================================

class TestPomodoroTool:

    @pytest.fixture(autouse=True)
    def reset_global_state(self):
        """Resetea el estado global del modulo antes de cada test."""
        # Detener cualquier timer previo y esperar a que el thread termine
        pomodoro_module._timer_stop.set()
        if pomodoro_module._timer_thread is not None:
            pomodoro_module._timer_thread.join(timeout=2)
        pomodoro_module._active_timer = None
        pomodoro_module._timer_thread = None
        pomodoro_module._timer_stop.clear()
        yield
        # Cleanup: asegurar que timers se detengan
        pomodoro_module._timer_stop.set()
        if pomodoro_module._timer_thread is not None:
            pomodoro_module._timer_thread.join(timeout=2)
        pomodoro_module._active_timer = None
        pomodoro_module._timer_thread = None

    def test_start_timer(self):
        """Iniciar un timer Pomodoro exitosamente."""
        tool = PomodoroTool()
        result = tool.execute(action="start", minutes=25, label="coding")

        assert result.success
        assert "iniciado" in result.output.lower() or "Pomodoro" in result.output
        assert "coding" in result.output
        assert "25" in result.output
        assert pomodoro_module._active_timer is not None

    def test_start_when_already_active(self):
        """Iniciar timer cuando ya hay uno activo retorna error."""
        tool = PomodoroTool()

        # Primer start
        result1 = tool.execute(action="start", minutes=25, label="first")
        assert result1.success

        # Segundo start deberia fallar
        result2 = tool.execute(action="start", minutes=10, label="second")
        assert not result2.success
        assert "activo" in result2.error.lower() or "timer" in result2.error.lower()

    def test_stop_timer(self):
        """Detener un timer activo exitosamente."""
        tool = PomodoroTool()

        # Iniciar
        tool.execute(action="start", minutes=25, label="working")

        # Detener
        result = tool.execute(action="stop")

        assert result.success
        assert "cancelado" in result.output.lower() or "working" in result.output

    def test_stop_no_timer(self):
        """Detener cuando no hay timer activo retorna error."""
        tool = PomodoroTool()
        result = tool.execute(action="stop")

        assert not result.success
        assert "no hay" in result.error.lower() or "timer" in result.error.lower()

    def test_status_no_timer(self):
        """Status sin timer activo muestra info correcta."""
        tool = PomodoroTool()
        result = tool.execute(action="status")

        assert result.success
        assert "no hay" in result.output.lower() or "No hay timer" in result.output
        assert "completados" in result.output.lower() or "Pomodoros" in result.output

    def test_status_active_timer(self):
        """Status con timer activo muestra label, duracion y restante."""
        tool = PomodoroTool()

        # Iniciar
        tool.execute(action="start", minutes=25, label="deep work")

        # Esperar un instante para tener algun transcurrido
        time.sleep(0.05)

        # Status
        result = tool.execute(action="status")

        assert result.success
        assert "deep work" in result.output
        assert "25" in result.output
        assert "Restante" in result.output or "restante" in result.output.lower()

    def test_unknown_action(self):
        """Accion desconocida retorna error."""
        tool = PomodoroTool()
        result = tool.execute(action="dance")

        assert not result.success
        assert "desconocida" in result.error.lower() or "dance" in result.error

    def test_tool_metadata(self):
        """Tool tiene nombre, descripcion y parametros correctos."""
        tool = PomodoroTool()

        assert tool.name == "pomodoro"
        assert "pomodoro" in tool.description.lower() or "timer" in tool.description.lower()

        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "action" in params["properties"]
        assert "minutes" in params["properties"]
        assert "label" in params["properties"]
        assert "action" in params["required"]

        defn = tool.to_claude_definition()
        assert defn["name"] == "pomodoro"
        assert "input_schema" in defn
        assert "description" in defn
