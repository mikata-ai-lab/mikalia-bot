"""
test_csv_analyzer.py — Tests para CsvAnalyzerTool.

Verifica:
- Preview de CSV (raw_data y file_path)
- Stats de columnas numericas
- Summary con archivo
- Formato JSON
- Archivos no encontrados
- Datos vacios
- Definiciones Claude correctas
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mikalia.tools.csv_analyzer import CsvAnalyzerTool


# ================================================================
# CsvAnalyzerTool — preview
# ================================================================

class TestCsvPreview:
    def test_preview_csv(self):
        """Preview de raw_data CSV muestra headers y filas."""
        tool = CsvAnalyzerTool()
        csv_data = "name,age,city\nAlice,30,Tokyo\nBob,25,Osaka\nCharlie,35,Kyoto"
        result = tool.execute(action="preview", raw_data=csv_data)

        assert result.success
        assert "name" in result.output
        assert "age" in result.output
        assert "Alice" in result.output
        assert "Bob" in result.output
        assert "Charlie" in result.output

    def test_preview_truncates_long_rows(self):
        """Preview con muchas filas muestra indicador de filas restantes."""
        tool = CsvAnalyzerTool()
        rows = ["id,value"]
        for i in range(20):
            rows.append(f"{i},{i * 10}")
        csv_data = "\n".join(rows)

        result = tool.execute(action="preview", raw_data=csv_data)
        assert result.success
        assert "filas mas" in result.output


# ================================================================
# CsvAnalyzerTool — stats
# ================================================================

class TestCsvStats:
    def test_stats_numeric_columns(self):
        """Stats calcula mean, median, stdev para columnas numericas."""
        tool = CsvAnalyzerTool()
        csv_data = "name,score,rating\nA,85,4.5\nB,90,3.8\nC,78,4.2\nD,92,4.9\nE,88,3.5"
        result = tool.execute(action="stats", raw_data=csv_data)

        assert result.success
        assert "score" in result.output
        assert "Mean" in result.output
        assert "Median" in result.output
        assert "Stdev" in result.output
        assert "Min" in result.output
        assert "Max" in result.output

    def test_stats_no_numeric_columns(self):
        """Stats sin columnas numericas retorna mensaje informativo."""
        tool = CsvAnalyzerTool()
        csv_data = "name,city\nAlice,Tokyo\nBob,Osaka"
        result = tool.execute(action="stats", raw_data=csv_data)

        assert result.success
        assert "No se encontraron columnas numericas" in result.output


# ================================================================
# CsvAnalyzerTool — summary
# ================================================================

class TestCsvSummary:
    def test_summary_with_file(self, tmp_path):
        """Summary desde archivo muestra info del dataset."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "name,age,city\nAlice,30,Tokyo\nBob,25,Osaka\nCharlie,35,Kyoto",
            encoding="utf-8",
        )

        tool = CsvAnalyzerTool()
        result = tool.execute(action="summary", file_path=str(csv_file))

        assert result.success
        assert "Filas: 3" in result.output
        assert "Columnas: 3" in result.output
        assert "name" in result.output
        assert str(csv_file) in result.output

    def test_summary_detects_types(self):
        """Summary detecta tipos de columnas (numeric, text)."""
        tool = CsvAnalyzerTool()
        csv_data = "name,score\nAlice,85\nBob,90"
        result = tool.execute(action="summary", raw_data=csv_data)

        assert result.success
        assert "text" in result.output
        assert "numeric" in result.output


# ================================================================
# CsvAnalyzerTool — JSON format
# ================================================================

class TestCsvJsonFormat:
    def test_json_format(self):
        """Acepta datos en formato JSON."""
        tool = CsvAnalyzerTool()
        json_data = json.dumps([
            {"name": "Alice", "score": 85},
            {"name": "Bob", "score": 90},
        ])
        result = tool.execute(action="preview", raw_data=json_data, format="json")

        assert result.success
        assert "Alice" in result.output
        assert "Bob" in result.output

    def test_json_auto_detect(self):
        """Auto-detecta formato JSON cuando empieza con [."""
        tool = CsvAnalyzerTool()
        json_data = json.dumps([
            {"language": "Python", "year": 1991},
            {"language": "Rust", "year": 2010},
        ])
        result = tool.execute(action="preview", raw_data=json_data)

        assert result.success
        assert "Python" in result.output


# ================================================================
# CsvAnalyzerTool — error handling
# ================================================================

class TestCsvErrors:
    def test_file_not_found(self):
        """Archivo inexistente retorna error."""
        tool = CsvAnalyzerTool()
        result = tool.execute(action="preview", file_path="/nonexistent/data.csv")

        assert not result.success
        assert "no encontrado" in result.error.lower()

    def test_empty_data(self):
        """Sin file_path ni raw_data retorna error."""
        tool = CsvAnalyzerTool()
        result = tool.execute(action="preview")

        assert not result.success
        assert "file_path" in result.error.lower() or "raw_data" in result.error.lower()


# ================================================================
# CsvAnalyzerTool — metadata
# ================================================================

class TestCsvMetadata:
    def test_tool_metadata(self):
        """Definicion Claude tiene formato correcto."""
        tool = CsvAnalyzerTool()
        assert tool.name == "csv_analyzer"
        assert "csv" in tool.description.lower()

        d = tool.to_claude_definition()
        assert d["name"] == "csv_analyzer"
        assert "action" in d["input_schema"]["properties"]
        assert "file_path" in d["input_schema"]["properties"]
        assert "raw_data" in d["input_schema"]["properties"]
        assert "action" in d["input_schema"]["required"]
