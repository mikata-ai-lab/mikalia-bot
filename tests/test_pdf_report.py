"""
test_pdf_report.py — Tests para PdfReportTool.

Verifica:
- Generacion de reporte basico
- Reporte con tabla
- JSON invalido en sections
- fpdf2 no instalado
- Definiciones Claude correctas
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mikalia.tools.pdf_report import PdfReportTool


# ================================================================
# Helpers
# ================================================================

def _make_mock_fpdf():
    """Crea mocks de fpdf.FPDF."""
    mock_fpdf_class = MagicMock()
    mock_fpdf_instance = MagicMock()
    mock_fpdf_class.return_value = mock_fpdf_instance
    # w atributo usado para calcular col_width en _add_table
    mock_fpdf_instance.w = 210
    return mock_fpdf_class, mock_fpdf_instance


# ================================================================
# PdfReportTool — report generation
# ================================================================

class TestPdfReportGeneration:
    def test_basic_report(self, tmp_path):
        """Genera un reporte PDF basico con secciones de texto."""
        mock_fpdf_class, mock_fpdf_instance = _make_mock_fpdf()

        sections = json.dumps([
            {"heading": "Introduccion", "content": "Este es un reporte de prueba."},
            {"heading": "Conclusiones", "content": "Todo funciona correctamente."},
        ])

        with patch("mikalia.tools.pdf_report.REPORTS_DIR", tmp_path):
            with patch.dict("sys.modules", {"fpdf": MagicMock(FPDF=mock_fpdf_class)}):
                tool = PdfReportTool()
                result = tool.execute(title="Test Report", sections=sections)

        assert result.success
        assert "Test Report" in result.output
        assert "Secciones: 2" in result.output
        mock_fpdf_instance.add_page.assert_called_once()
        mock_fpdf_instance.output.assert_called_once()

    def test_report_with_table(self, tmp_path):
        """Genera un reporte PDF con tabla."""
        mock_fpdf_class, mock_fpdf_instance = _make_mock_fpdf()

        sections = json.dumps([
            {
                "heading": "Datos",
                "table": {
                    "headers": ["Nombre", "Edad", "Ciudad"],
                    "rows": [
                        ["Alice", "30", "Tokyo"],
                        ["Bob", "25", "Osaka"],
                    ],
                },
            },
        ])

        with patch("mikalia.tools.pdf_report.REPORTS_DIR", tmp_path):
            with patch.dict("sys.modules", {"fpdf": MagicMock(FPDF=mock_fpdf_class)}):
                tool = PdfReportTool()
                result = tool.execute(title="Table Report", sections=sections)

        assert result.success
        assert "Table Report" in result.output
        # Verificar que se llamaron los metodos de celda para la tabla
        assert mock_fpdf_instance.cell.call_count > 0

    def test_report_with_author(self, tmp_path):
        """Reporte incluye autor personalizado."""
        mock_fpdf_class, mock_fpdf_instance = _make_mock_fpdf()

        sections = json.dumps([
            {"heading": "Seccion", "content": "Contenido"},
        ])

        with patch("mikalia.tools.pdf_report.REPORTS_DIR", tmp_path):
            with patch.dict("sys.modules", {"fpdf": MagicMock(FPDF=mock_fpdf_class)}):
                tool = PdfReportTool()
                result = tool.execute(
                    title="Report", sections=sections, author="Mikata"
                )

        assert result.success
        # El PDF se genero (output() llamado)
        mock_fpdf_instance.output.assert_called_once()


# ================================================================
# PdfReportTool — error handling
# ================================================================

class TestPdfReportErrors:
    def test_invalid_sections_json(self):
        """JSON invalido en sections retorna error."""
        mock_fpdf_class, _ = _make_mock_fpdf()

        with patch.dict("sys.modules", {"fpdf": MagicMock(FPDF=mock_fpdf_class)}):
            tool = PdfReportTool()
            result = tool.execute(title="Test", sections="not valid json {{{")

        assert not result.success
        assert "JSON invalido" in result.error

    def test_sections_not_array(self):
        """sections que no es array retorna error."""
        mock_fpdf_class, _ = _make_mock_fpdf()

        with patch.dict("sys.modules", {"fpdf": MagicMock(FPDF=mock_fpdf_class)}):
            tool = PdfReportTool()
            result = tool.execute(
                title="Test",
                sections=json.dumps({"heading": "solo", "content": "objeto"}),
            )

        assert not result.success
        assert "array" in result.error.lower()

    def test_fpdf_not_installed(self):
        """Sin fpdf2 retorna error descriptivo."""
        with patch.dict("sys.modules", {"fpdf": None}):
            tool = PdfReportTool()
            result = tool.execute(
                title="Test",
                sections=json.dumps([{"heading": "X", "content": "Y"}]),
            )

        assert not result.success
        assert "fpdf2" in result.error.lower()


# ================================================================
# PdfReportTool — metadata
# ================================================================

class TestPdfReportMetadata:
    def test_tool_metadata(self):
        """Definicion Claude tiene formato correcto."""
        tool = PdfReportTool()
        assert tool.name == "pdf_report"
        assert "pdf" in tool.description.lower()

        d = tool.to_claude_definition()
        assert d["name"] == "pdf_report"
        assert "title" in d["input_schema"]["properties"]
        assert "sections" in d["input_schema"]["properties"]
        assert "author" in d["input_schema"]["properties"]
        assert "title" in d["input_schema"]["required"]
        assert "sections" in d["input_schema"]["required"]
