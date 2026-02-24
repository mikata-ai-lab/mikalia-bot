"""
test_workflow_triggers.py — Tests para WorkflowTriggersTool.

Verifica:
- Creacion de triggers (evento -> accion)
- Listado de triggers activos
- Eliminacion de triggers
- Disparo de eventos con y sin triggers asociados
- Validacion de eventos y acciones
- Funcionamiento sin memoria (in-memory triggers)
- Metadata del tool
"""

from __future__ import annotations

import json

import pytest
from pathlib import Path

from mikalia.tools.workflow_triggers import (
    WorkflowTriggersTool,
    SUPPORTED_EVENTS,
    SUPPORTED_ACTIONS,
)
from mikalia.tools.base import ToolResult
from mikalia.core.memory import MemoryManager


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"


@pytest.fixture
def memory(tmp_path):
    """MemoryManager con DB temporal y alias _get_conn."""
    db = tmp_path / "test.db"
    mem = MemoryManager(db_path=str(db), schema_path=str(SCHEMA_PATH))
    # Los tools nuevos usan _get_conn; MemoryManager define _get_connection
    mem._get_conn = mem._get_connection
    return mem


# ================================================================
# CRUD de triggers
# ================================================================

class TestTriggerCRUD:
    def test_create_trigger(self, memory):
        """Crear un trigger con memoria persiste en SQLite."""
        tool = WorkflowTriggersTool(memory=memory)
        result = tool.execute(
            action="create",
            event="pomodoro_complete",
            trigger_action="notify",
            config=json.dumps({"message": "Pomodoro terminado!"}),
        )
        assert result.success
        assert "Trigger creado" in result.output
        assert "pomodoro_complete" in result.output
        assert "notify" in result.output

    def test_list_triggers(self, memory):
        """Listar triggers muestra los creados."""
        tool = WorkflowTriggersTool(memory=memory)

        # Crear dos triggers
        tool.execute(
            action="create",
            event="pomodoro_complete",
            trigger_action="notify",
            config="{}",
        )
        tool.execute(
            action="create",
            event="expense_added",
            trigger_action="log",
            config="{}",
        )

        result = tool.execute(action="list")
        assert result.success
        assert "Triggers" in result.output
        assert "pomodoro_complete" in result.output
        assert "expense_added" in result.output

    def test_delete_trigger(self, memory):
        """Eliminar un trigger lo remueve de la lista."""
        tool = WorkflowTriggersTool(memory=memory)

        # Crear trigger
        create_result = tool.execute(
            action="create",
            event="habit_complete",
            trigger_action="log",
            config="{}",
        )
        assert create_result.success
        # Extraer el ID del output
        trigger_id = int(
            create_result.output.split("ID: ")[1].split(")")[0]
        )

        # Eliminar
        delete_result = tool.execute(action="delete", trigger_id=trigger_id)
        assert delete_result.success
        assert "eliminado" in delete_result.output

        # Verificar que ya no aparece
        list_result = tool.execute(action="list")
        assert "habit_complete" not in list_result.output


# ================================================================
# Fire events
# ================================================================

class TestFireEvents:
    def test_fire_event(self, memory):
        """Disparar evento ejecuta triggers asociados."""
        tool = WorkflowTriggersTool(memory=memory)

        # Crear trigger de notificacion
        tool.execute(
            action="create",
            event="pomodoro_complete",
            trigger_action="notify",
            config=json.dumps({"message": "Bien hecho!"}),
        )

        result = tool.execute(
            action="fire",
            event="pomodoro_complete",
        )
        assert result.success
        assert "pomodoro_complete" in result.output
        assert "Triggers ejecutados: 1" in result.output

    def test_fire_no_triggers(self, memory):
        """Disparar evento sin triggers asociados indica que no hay."""
        tool = WorkflowTriggersTool(memory=memory)
        result = tool.execute(
            action="fire",
            event="daily_brief",
        )
        assert result.success
        assert "No hay triggers asociados" in result.output


# ================================================================
# Validacion
# ================================================================

class TestTriggerValidation:
    def test_invalid_event(self, memory):
        """Evento desconocido es rechazado."""
        tool = WorkflowTriggersTool(memory=memory)
        result = tool.execute(
            action="create",
            event="evento_fantasma",
            trigger_action="notify",
        )
        assert not result.success
        assert "Evento desconocido" in result.error

    def test_invalid_action(self, memory):
        """Accion desconocida es rechazada."""
        tool = WorkflowTriggersTool(memory=memory)
        result = tool.execute(
            action="create",
            event="pomodoro_complete",
            trigger_action="hackear",
        )
        assert not result.success
        assert "Accion desconocida" in result.error


# ================================================================
# Sin memoria (in-memory triggers)
# ================================================================

class TestTriggersWithoutMemory:
    def test_without_memory(self):
        """Triggers funcionan en memoria cuando no hay MemoryManager."""
        tool = WorkflowTriggersTool(memory=None)

        # Crear trigger in-memory
        create_result = tool.execute(
            action="create",
            event="custom",
            trigger_action="log",
            config=json.dumps({"message": "Test sin DB"}),
        )
        assert create_result.success

        # Listar
        list_result = tool.execute(action="list")
        assert list_result.success
        assert "custom" in list_result.output

        # Disparar
        fire_result = tool.execute(action="fire", event="custom")
        assert fire_result.success
        assert "Triggers ejecutados: 1" in fire_result.output

    def test_without_memory_delete(self):
        """Delete sin memoria remueve de la lista in-memory."""
        tool = WorkflowTriggersTool(memory=None)

        tool.execute(
            action="create",
            event="message_received",
            trigger_action="notify",
            config="{}",
        )

        # Trigger ID sera 1 (len + 1)
        delete_result = tool.execute(action="delete", trigger_id=1)
        assert delete_result.success

        list_result = tool.execute(action="list")
        assert "No hay triggers" in list_result.output


# ================================================================
# Metadata
# ================================================================

class TestWorkflowTriggersMetadata:
    def test_tool_metadata(self):
        """Metadata del tool es correcta."""
        tool = WorkflowTriggersTool()
        assert tool.name == "workflow_triggers"
        assert "trigger" in tool.description.lower()

        defn = tool.to_claude_definition()
        assert defn["name"] == "workflow_triggers"
        assert "input_schema" in defn
        assert "action" in defn["input_schema"]["properties"]
        assert "event" in defn["input_schema"]["properties"]
        assert "trigger_action" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["properties"]["action"]["enum"] == [
            "create", "list", "delete", "fire"
        ]
