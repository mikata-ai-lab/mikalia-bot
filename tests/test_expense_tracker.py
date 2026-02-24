"""
test_expense_tracker.py — Tests para ExpenseTrackerTool.

Verifica:
- Registro de gastos e ingresos
- Validacion de montos y categorias
- Reporte de resumen por periodo
- Listado de transacciones
- Balance general
- Error sin MemoryManager
- Metadata del tool
"""

from __future__ import annotations

import pytest
from pathlib import Path

from mikalia.tools.expense_tracker import ExpenseTrackerTool
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
# Add / validacion
# ================================================================

class TestAddExpense:
    def test_add_expense(self, memory):
        """Registrar un gasto basico."""
        tool = ExpenseTrackerTool(memory=memory)
        result = tool.execute(
            action="add",
            amount=150.0,
            category="comida",
            description="Tacos",
            type="expense",
        )
        assert result.success
        assert "150.00" in result.output
        assert "comida" in result.output
        assert "expense" in result.output

    def test_add_income(self, memory):
        """Registrar un ingreso."""
        tool = ExpenseTrackerTool(memory=memory)
        result = tool.execute(
            action="add",
            amount=5000.0,
            category="salario",
            description="Pago mensual",
            type="income",
        )
        assert result.success
        assert "income" in result.output
        assert "5000.00" in result.output
        assert "salario" in result.output

    def test_invalid_amount(self, memory):
        """Monto cero o negativo es rechazado."""
        tool = ExpenseTrackerTool(memory=memory)

        result_zero = tool.execute(
            action="add", amount=0, category="comida", type="expense"
        )
        assert not result_zero.success
        assert "mayor a 0" in result_zero.error

        result_neg = tool.execute(
            action="add", amount=-10, category="comida", type="expense"
        )
        assert not result_neg.success
        assert "mayor a 0" in result_neg.error

    def test_missing_category(self, memory):
        """Categoria vacia es rechazada."""
        tool = ExpenseTrackerTool(memory=memory)
        result = tool.execute(
            action="add", amount=100, category="", type="expense"
        )
        assert not result.success
        assert "Categoria requerida" in result.error


# ================================================================
# Consultas
# ================================================================

class TestExpenseQueries:
    def test_summary_report(self, memory):
        """Resumen muestra gastos e ingresos por categoria."""
        tool = ExpenseTrackerTool(memory=memory)

        # Agregar datos
        tool.execute(action="add", amount=100, category="comida", type="expense")
        tool.execute(action="add", amount=200, category="comida", type="expense")
        tool.execute(action="add", amount=50, category="transporte", type="expense")
        tool.execute(action="add", amount=5000, category="salario", type="income")

        result = tool.execute(action="summary", days=30)
        assert result.success
        assert "Resumen financiero" in result.output
        assert "comida" in result.output
        assert "transporte" in result.output
        assert "salario" in result.output
        assert "TOTAL GASTOS" in result.output
        assert "TOTAL INGRESOS" in result.output
        assert "Balance" in result.output

    def test_list_transactions(self, memory):
        """Listar transacciones recientes."""
        tool = ExpenseTrackerTool(memory=memory)

        tool.execute(action="add", amount=80, category="comida", description="Sushi", type="expense")
        tool.execute(action="add", amount=3000, category="freelance", description="Proyecto X", type="income")

        result = tool.execute(action="list", days=30)
        assert result.success
        assert "Sushi" in result.output or "comida" in result.output
        assert "Proyecto X" in result.output or "freelance" in result.output

    def test_balance(self, memory):
        """Balance calcula ingresos - gastos."""
        tool = ExpenseTrackerTool(memory=memory)

        tool.execute(action="add", amount=1000, category="salario", type="income")
        tool.execute(action="add", amount=300, category="comida", type="expense")

        result = tool.execute(action="balance", days=30)
        assert result.success
        assert "Ingresos" in result.output
        assert "Gastos" in result.output
        assert "Balance" in result.output
        assert "1000.00" in result.output
        assert "300.00" in result.output


# ================================================================
# Edge cases
# ================================================================

class TestExpenseEdgeCases:
    def test_no_memory_error(self):
        """Sin MemoryManager retorna error."""
        tool = ExpenseTrackerTool(memory=None)
        result = tool.execute(action="add", amount=100, category="comida")
        assert not result.success
        assert "MemoryManager" in result.error

    def test_tool_metadata(self):
        """Metadata del tool es correcta."""
        tool = ExpenseTrackerTool()
        assert tool.name == "expense_tracker"
        assert "expense" in tool.description.lower() or "Track" in tool.description

        defn = tool.to_claude_definition()
        assert defn["name"] == "expense_tracker"
        assert "input_schema" in defn
        assert "action" in defn["input_schema"]["properties"]
        assert "amount" in defn["input_schema"]["properties"]
        assert "category" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["properties"]["action"]["enum"] == [
            "add", "summary", "list", "balance"
        ]
