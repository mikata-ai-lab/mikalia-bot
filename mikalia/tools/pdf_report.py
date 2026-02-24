"""
pdf_report.py — Generacion de reportes PDF para Mikalia.

Genera reportes PDF simples sin dependencias externas pesadas.
Usa fpdf2 (ligera, puro Python).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.pdf_report")

REPORTS_DIR = Path("data/reports")


class PdfReportTool(BaseTool):
    """Genera reportes PDF con texto, tablas y secciones."""

    @property
    def name(self) -> str:
        return "pdf_report"

    @property
    def description(self) -> str:
        return (
            "Generate PDF reports with sections, text, and tables. "
            "Provide a title, sections with content, and optional tables. "
            "Returns the file path of the generated PDF."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Report title",
                },
                "sections": {
                    "type": "string",
                    "description": (
                        "JSON array of sections. Each: "
                        '{"heading": "...", "content": "..."} or '
                        '{"heading": "...", "table": {"headers": [...], "rows": [[...]]}}'
                    ),
                },
                "author": {
                    "type": "string",
                    "description": "Report author (default: Mikalia)",
                },
            },
            "required": ["title", "sections"],
        }

    def execute(
        self,
        title: str,
        sections: str,
        author: str = "Mikalia",
        **_: Any,
    ) -> ToolResult:
        try:
            from fpdf import FPDF
        except ImportError:
            return ToolResult(
                success=False,
                error="fpdf2 no instalado. Ejecuta: pip install fpdf2",
            )

        import json

        try:
            section_list = json.loads(sections)
        except json.JSONDecodeError as e:
            return ToolResult(success=False, error=f"JSON invalido en sections: {e}")

        if not isinstance(section_list, list):
            return ToolResult(success=False, error="sections debe ser un JSON array")

        try:
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()

            # Titulo
            pdf.set_font("Helvetica", "B", 20)
            pdf.cell(0, 15, title, ln=True, align="C")
            pdf.ln(5)

            # Autor y fecha
            pdf.set_font("Helvetica", "I", 10)
            pdf.cell(0, 8, f"Autor: {author}", ln=True, align="C")
            pdf.cell(
                0, 8,
                f"Fecha: {time.strftime('%Y-%m-%d %H:%M')}",
                ln=True, align="C",
            )
            pdf.ln(10)

            # Secciones
            for section in section_list:
                heading = section.get("heading", "")
                content = section.get("content", "")
                table = section.get("table")

                if heading:
                    pdf.set_font("Helvetica", "B", 14)
                    pdf.cell(0, 10, heading, ln=True)
                    pdf.ln(3)

                if content:
                    pdf.set_font("Helvetica", "", 11)
                    pdf.multi_cell(0, 6, content)
                    pdf.ln(5)

                if table:
                    self._add_table(pdf, table)
                    pdf.ln(5)

            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"report_{int(time.time())}.pdf"
            filepath = REPORTS_DIR / filename
            pdf.output(str(filepath))

            logger.success(f"PDF generado: {filepath}")
            return ToolResult(
                success=True,
                output=(
                    f"Reporte PDF generado: {filepath}\n"
                    f"Titulo: {title}\n"
                    f"Secciones: {len(section_list)}"
                ),
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Error generando PDF: {e}")

    def _add_table(self, pdf: Any, table: dict) -> None:
        """Agrega una tabla al PDF."""
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        if not headers:
            return

        col_width = (pdf.w - 20) / len(headers)

        # Header
        pdf.set_font("Helvetica", "B", 10)
        for h in headers:
            pdf.cell(col_width, 8, str(h)[:20], border=1, align="C")
        pdf.ln()

        # Rows
        pdf.set_font("Helvetica", "", 9)
        for row in rows[:50]:  # Max 50 rows
            for i, cell in enumerate(row):
                if i < len(headers):
                    pdf.cell(col_width, 7, str(cell)[:25], border=1)
            pdf.ln()
