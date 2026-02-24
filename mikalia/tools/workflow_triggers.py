"""
workflow_triggers.py — Sistema de triggers para Mikalia.

Permite crear automatizaciones: cuando pasa X, haz Y.
Ejemplo: "cuando se complete un pomodoro, envia un mensaje"
"""

from __future__ import annotations

import json
from typing import Any, Callable

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.workflow_triggers")

# Eventos soportados
SUPPORTED_EVENTS = [
    "pomodoro_complete",
    "habit_complete",
    "expense_added",
    "goal_updated",
    "daily_brief",
    "message_received",
    "error_occurred",
    "custom",
]

# Acciones soportadas
SUPPORTED_ACTIONS = [
    "notify",        # Enviar notificacion
    "log",           # Registrar en log
    "add_fact",      # Guardar en memoria
    "run_tool",      # Ejecutar otro tool
]


class WorkflowTriggersTool(BaseTool):
    """Sistema de triggers y automatizaciones."""

    def __init__(self, memory=None) -> None:
        self._memory = memory
        self._triggers: list[dict] = []
        self._callbacks: dict[str, list[Callable]] = {}
        self._initialized = False

    @property
    def name(self) -> str:
        return "workflow_triggers"

    @property
    def description(self) -> str:
        return (
            "Create automation triggers. Actions: "
            "create (define a new trigger: event → action), "
            "list (show all triggers), "
            "delete (remove a trigger), "
            "fire (manually fire an event for testing). "
            "Events: pomodoro_complete, habit_complete, expense_added, "
            "goal_updated, daily_brief, message_received, custom."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: create, list, delete, fire",
                    "enum": ["create", "list", "delete", "fire"],
                },
                "event": {
                    "type": "string",
                    "description": "Event name to trigger on",
                },
                "trigger_action": {
                    "type": "string",
                    "description": "Action to perform: notify, log, add_fact, run_tool",
                },
                "config": {
                    "type": "string",
                    "description": (
                        "JSON config for the action. "
                        'For notify: {"message": "..."}. '
                        'For run_tool: {"tool": "...", "params": {...}}.'
                    ),
                },
                "trigger_id": {
                    "type": "integer",
                    "description": "Trigger ID (for delete)",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        event: str = "",
        trigger_action: str = "",
        config: str = "{}",
        trigger_id: int = -1,
        **_: Any,
    ) -> ToolResult:
        self._ensure_loaded()

        if action == "create":
            return self._create(event, trigger_action, config)
        elif action == "list":
            return self._list()
        elif action == "delete":
            return self._delete(trigger_id)
        elif action == "fire":
            return self._fire(event, config)
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _ensure_loaded(self) -> None:
        """Carga triggers de memoria si existen."""
        if self._initialized:
            return
        if self._memory:
            conn = self._memory._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_triggers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    action TEXT NOT NULL,
                    config TEXT DEFAULT '{}',
                    active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_fired TEXT
                )
            """)
            conn.commit()

            rows = conn.execute(
                "SELECT id, event, action, config FROM workflow_triggers WHERE active = 1"
            ).fetchall()
            self._triggers = [
                {"id": r[0], "event": r[1], "action": r[2], "config": json.loads(r[3])}
                for r in rows
            ]
        self._initialized = True

    def _create(self, event: str, trigger_action: str, config_str: str) -> ToolResult:
        if not event:
            return ToolResult(success=False, error="Evento requerido")
        if event not in SUPPORTED_EVENTS:
            return ToolResult(
                success=False,
                error=f"Evento desconocido: {event}. Validos: {', '.join(SUPPORTED_EVENTS)}",
            )
        if trigger_action not in SUPPORTED_ACTIONS:
            return ToolResult(
                success=False,
                error=f"Accion desconocida: {trigger_action}. Validas: {', '.join(SUPPORTED_ACTIONS)}",
            )

        try:
            config = json.loads(config_str) if config_str else {}
        except json.JSONDecodeError:
            config = {}

        if self._memory:
            conn = self._memory._get_conn()
            cursor = conn.execute(
                "INSERT INTO workflow_triggers (event, action, config) VALUES (?, ?, ?)",
                (event, trigger_action, json.dumps(config)),
            )
            conn.commit()
            trigger_id = cursor.lastrowid
        else:
            trigger_id = len(self._triggers) + 1

        trigger = {
            "id": trigger_id,
            "event": event,
            "action": trigger_action,
            "config": config,
        }
        self._triggers.append(trigger)

        logger.success(f"Trigger creado: {event} → {trigger_action}")
        return ToolResult(
            success=True,
            output=(
                f"Trigger creado (ID: {trigger_id}):\n"
                f"  Cuando: {event}\n"
                f"  Hacer: {trigger_action}\n"
                f"  Config: {json.dumps(config)}"
            ),
        )

    def _list(self) -> ToolResult:
        if not self._triggers:
            return ToolResult(success=True, output="No hay triggers configurados.")

        lines = [f"=== Triggers ({len(self._triggers)}) ==="]
        for t in self._triggers:
            lines.append(
                f"  #{t['id']}: {t['event']} → {t['action']} "
                f"({json.dumps(t['config'])})"
            )
        return ToolResult(success=True, output="\n".join(lines))

    def _delete(self, trigger_id: int) -> ToolResult:
        if trigger_id < 0:
            return ToolResult(success=False, error="trigger_id requerido")

        if self._memory:
            conn = self._memory._get_conn()
            result = conn.execute(
                "UPDATE workflow_triggers SET active = 0 WHERE id = ?",
                (trigger_id,),
            )
            conn.commit()
            if result.rowcount == 0:
                return ToolResult(success=False, error=f"Trigger {trigger_id} no encontrado")

        self._triggers = [t for t in self._triggers if t["id"] != trigger_id]
        return ToolResult(success=True, output=f"Trigger #{trigger_id} eliminado.")

    def _fire(self, event: str, data_str: str) -> ToolResult:
        """Dispara un evento y ejecuta triggers asociados."""
        if not event:
            return ToolResult(success=False, error="Evento requerido")

        try:
            data = json.loads(data_str) if data_str else {}
        except json.JSONDecodeError:
            data = {}

        matched = [t for t in self._triggers if t["event"] == event]

        if not matched:
            return ToolResult(
                success=True,
                output=f"Evento '{event}' disparado. No hay triggers asociados.",
            )

        results = []
        for trigger in matched:
            action_result = self._execute_action(trigger, data)
            results.append(f"  #{trigger['id']} ({trigger['action']}): {action_result}")

            if self._memory:
                conn = self._memory._get_conn()
                conn.execute(
                    "UPDATE workflow_triggers SET last_fired = datetime('now') WHERE id = ?",
                    (trigger["id"],),
                )
                conn.commit()

        return ToolResult(
            success=True,
            output=(
                f"Evento '{event}' disparado.\n"
                f"Triggers ejecutados: {len(matched)}\n"
                + "\n".join(results)
            ),
        )

    def _execute_action(self, trigger: dict, data: dict) -> str:
        """Ejecuta la accion de un trigger."""
        action = trigger["action"]
        config = trigger["config"]

        if action == "notify":
            msg = config.get("message", f"Trigger fired: {trigger['event']}")
            return f"Notificacion: {msg}"

        elif action == "log":
            msg = config.get("message", f"Event: {trigger['event']}")
            logger.info(f"[Trigger] {msg}")
            return f"Logged: {msg}"

        elif action == "add_fact":
            if self._memory:
                subject = config.get("subject", trigger["event"])
                fact = config.get("fact", json.dumps(data))
                self._memory.add_fact("automation", subject, fact)
                return f"Fact guardado: {subject}"
            return "Sin memoria disponible"

        elif action == "run_tool":
            tool_name = config.get("tool", "")
            return f"Tool '{tool_name}' programado para ejecucion"

        return "Accion no implementada"

    def fire_event(self, event: str, data: dict | None = None) -> list[str]:
        """API publica para disparar eventos desde otros modulos."""
        self._ensure_loaded()
        matched = [t for t in self._triggers if t["event"] == event]
        results = []
        for trigger in matched:
            result = self._execute_action(trigger, data or {})
            results.append(result)
        return results
