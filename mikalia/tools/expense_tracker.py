"""
expense_tracker.py — Tracker de gastos para Mikalia.

Registra ingresos y gastos en SQLite.
Categoriza, totaliza, y genera reportes por periodo.
"""

from __future__ import annotations

from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.expense_tracker")

EXPENSES_SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    description TEXT DEFAULT '',
    type TEXT DEFAULT 'expense',
    currency TEXT DEFAULT 'MXN',
    created_at TEXT DEFAULT (datetime('now'))
);
"""


class ExpenseTrackerTool(BaseTool):
    """Tracker de gastos e ingresos personales."""

    def __init__(self, memory=None) -> None:
        self._memory = memory
        self._initialized = False

    @property
    def name(self) -> str:
        return "expense_tracker"

    @property
    def description(self) -> str:
        return (
            "Track personal expenses and income. Actions: "
            "add (record expense or income), "
            "summary (totals by category for a period), "
            "list (recent transactions), "
            "balance (current balance). "
            "Default currency: MXN."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: add, summary, list, balance",
                    "enum": ["add", "summary", "list", "balance"],
                },
                "amount": {
                    "type": "number",
                    "description": "Amount (positive number)",
                },
                "category": {
                    "type": "string",
                    "description": "Category (e.g., comida, transporte, salario, freelance)",
                },
                "description": {
                    "type": "string",
                    "description": "Transaction description",
                },
                "type": {
                    "type": "string",
                    "description": "Type: expense or income (default: expense)",
                    "enum": ["expense", "income"],
                },
                "days": {
                    "type": "integer",
                    "description": "Period in days for summary/list (default: 30)",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        amount: float = 0,
        category: str = "",
        description: str = "",
        type: str = "expense",
        days: int = 30,
        **_: Any,
    ) -> ToolResult:
        if not self._memory:
            return ToolResult(
                success=False,
                error="Expense tracker necesita MemoryManager para funcionar",
            )

        self._ensure_tables()

        if action == "add":
            return self._add(amount, category, description, type)
        elif action == "summary":
            return self._summary(days)
        elif action == "list":
            return self._list(days)
        elif action == "balance":
            return self._balance(days)
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _ensure_tables(self) -> None:
        if self._initialized:
            return
        conn = self._memory._get_conn()
        conn.executescript(EXPENSES_SCHEMA)
        conn.commit()
        self._initialized = True

    def _add(
        self, amount: float, category: str, description: str, txn_type: str
    ) -> ToolResult:
        if amount <= 0:
            return ToolResult(success=False, error="Monto debe ser mayor a 0")
        if not category:
            return ToolResult(success=False, error="Categoria requerida")

        conn = self._memory._get_conn()
        conn.execute(
            "INSERT INTO expenses (amount, category, description, type) VALUES (?, ?, ?, ?)",
            (amount, category, description, txn_type),
        )
        conn.commit()

        emoji = "+" if txn_type == "income" else "-"
        logger.success(f"Transaccion: {emoji}${amount:.2f} ({category})")
        return ToolResult(
            success=True,
            output=(
                f"Registrado: {txn_type}\n"
                f"Monto: ${amount:.2f} MXN\n"
                f"Categoria: {category}\n"
                f"Descripcion: {description or '(sin descripcion)'}"
            ),
        )

    def _summary(self, days: int) -> ToolResult:
        conn = self._memory._get_conn()

        # Gastos por categoria
        expenses = conn.execute(
            "SELECT category, SUM(amount) as total, COUNT(*) as cnt "
            "FROM expenses WHERE type = 'expense' "
            "AND created_at >= datetime('now', ?) "
            "GROUP BY category ORDER BY total DESC",
            (f"-{days} days",),
        ).fetchall()

        # Ingresos por categoria
        income = conn.execute(
            "SELECT category, SUM(amount) as total, COUNT(*) as cnt "
            "FROM expenses WHERE type = 'income' "
            "AND created_at >= datetime('now', ?) "
            "GROUP BY category ORDER BY total DESC",
            (f"-{days} days",),
        ).fetchall()

        lines = [f"=== Resumen financiero (ultimos {days} dias) ==="]

        total_expense = 0
        if expenses:
            lines.append("\nGastos:")
            for cat, total, cnt in expenses:
                lines.append(f"  {cat}: ${total:.2f} ({cnt} transacciones)")
                total_expense += total
            lines.append(f"  TOTAL GASTOS: ${total_expense:.2f}")

        total_income = 0
        if income:
            lines.append("\nIngresos:")
            for cat, total, cnt in income:
                lines.append(f"  {cat}: ${total:.2f} ({cnt} transacciones)")
                total_income += total
            lines.append(f"  TOTAL INGRESOS: ${total_income:.2f}")

        balance = total_income - total_expense
        lines.append(f"\nBalance: ${balance:+.2f} MXN")

        return ToolResult(success=True, output="\n".join(lines))

    def _list(self, days: int) -> ToolResult:
        conn = self._memory._get_conn()
        rows = conn.execute(
            "SELECT type, amount, category, description, created_at "
            "FROM expenses WHERE created_at >= datetime('now', ?) "
            "ORDER BY created_at DESC LIMIT 20",
            (f"-{days} days",),
        ).fetchall()

        if not rows:
            return ToolResult(
                success=True,
                output=f"No hay transacciones en los ultimos {days} dias.",
            )

        lines = [f"Ultimas transacciones ({days} dias):"]
        for txn_type, amount, category, desc, date in rows:
            sign = "+" if txn_type == "income" else "-"
            lines.append(
                f"  {date[:10]} {sign}${amount:.2f} [{category}] {desc}"
            )

        return ToolResult(success=True, output="\n".join(lines))

    def _balance(self, days: int) -> ToolResult:
        conn = self._memory._get_conn()

        total_income = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses "
            "WHERE type = 'income' AND created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()[0]

        total_expense = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses "
            "WHERE type = 'expense' AND created_at >= datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()[0]

        balance = total_income - total_expense

        return ToolResult(
            success=True,
            output=(
                f"Balance (ultimos {days} dias):\n"
                f"  Ingresos: ${total_income:.2f}\n"
                f"  Gastos: ${total_expense:.2f}\n"
                f"  Balance: ${balance:+.2f} MXN"
            ),
        )
