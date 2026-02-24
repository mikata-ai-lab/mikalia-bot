"""
csv_analyzer.py — Analisis de CSV/JSON para Mikalia.

Lee archivos CSV o JSON y genera estadisticas,
previews, y resúmenes sin dependencias externas.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.csv_analyzer")

MAX_ROWS_PREVIEW = 10
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class CsvAnalyzerTool(BaseTool):
    """Analiza archivos CSV y JSON: stats, preview, resumen."""

    @property
    def name(self) -> str:
        return "csv_analyzer"

    @property
    def description(self) -> str:
        return (
            "Analyze CSV or JSON data files. Actions: "
            "preview (show first rows), "
            "stats (column statistics for numeric data), "
            "summary (row count, columns, types). "
            "Provide file path or raw data string."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: preview, stats, or summary",
                    "enum": ["preview", "stats", "summary"],
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to CSV or JSON file",
                },
                "raw_data": {
                    "type": "string",
                    "description": "Raw CSV or JSON string (alternative to file_path)",
                },
                "format": {
                    "type": "string",
                    "description": "Data format: csv or json (auto-detected from extension)",
                    "enum": ["csv", "json"],
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        file_path: str = "",
        raw_data: str = "",
        format: str = "",
        **_: Any,
    ) -> ToolResult:
        rows, headers, err = self._load_data(file_path, raw_data, format)
        if err:
            return ToolResult(success=False, error=err)

        if action == "preview":
            return self._preview(rows, headers)
        elif action == "stats":
            return self._stats(rows, headers)
        elif action == "summary":
            return self._summary(rows, headers, file_path)
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _load_data(
        self, file_path: str, raw_data: str, fmt: str
    ) -> tuple[list[dict], list[str], str | None]:
        """Carga datos de archivo o string. Returns (rows, headers, error)."""
        content = ""

        if file_path:
            path = Path(file_path)
            if not path.exists():
                return [], [], f"Archivo no encontrado: {file_path}"
            if path.stat().st_size > MAX_FILE_SIZE:
                return [], [], f"Archivo muy grande (max {MAX_FILE_SIZE // 1024 // 1024}MB)"
            content = path.read_text(encoding="utf-8")
            if not fmt:
                fmt = "json" if path.suffix.lower() == ".json" else "csv"
        elif raw_data:
            content = raw_data
            if not fmt:
                fmt = "json" if raw_data.strip().startswith(("[", "{")) else "csv"
        else:
            return [], [], "Proporciona file_path o raw_data"

        try:
            if fmt == "json":
                data = json.loads(content)
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    headers = list(data[0].keys())
                    return data, headers, None
                elif isinstance(data, dict):
                    return [data], list(data.keys()), None
                else:
                    return [], [], "JSON debe ser una lista de objetos o un objeto"
            else:
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)
                headers = reader.fieldnames or []
                return rows, list(headers), None
        except (json.JSONDecodeError, csv.Error) as e:
            return [], [], f"Error parseando datos: {e}"

    def _preview(self, rows: list[dict], headers: list[str]) -> ToolResult:
        """Muestra las primeras filas."""
        preview = rows[:MAX_ROWS_PREVIEW]
        lines = [" | ".join(headers)]
        lines.append("-" * len(lines[0]))
        for row in preview:
            values = [str(row.get(h, ""))[:30] for h in headers]
            lines.append(" | ".join(values))

        if len(rows) > MAX_ROWS_PREVIEW:
            lines.append(f"... y {len(rows) - MAX_ROWS_PREVIEW} filas mas")

        return ToolResult(success=True, output="\n".join(lines))

    def _stats(self, rows: list[dict], headers: list[str]) -> ToolResult:
        """Estadisticas de columnas numericas."""
        lines = []
        for h in headers:
            values = []
            for row in rows:
                try:
                    values.append(float(row.get(h, "")))
                except (ValueError, TypeError):
                    continue

            if len(values) < 2:
                continue

            lines.append(f"=== {h} ===")
            lines.append(f"  Count: {len(values)}")
            lines.append(f"  Mean: {statistics.mean(values):.2f}")
            lines.append(f"  Median: {statistics.median(values):.2f}")
            lines.append(f"  Stdev: {statistics.stdev(values):.2f}")
            lines.append(f"  Min: {min(values):.2f}")
            lines.append(f"  Max: {max(values):.2f}")

        if not lines:
            return ToolResult(
                success=True,
                output="No se encontraron columnas numericas con suficientes datos.",
            )

        return ToolResult(success=True, output="\n".join(lines))

    def _summary(
        self, rows: list[dict], headers: list[str], file_path: str
    ) -> ToolResult:
        """Resumen general del dataset."""
        lines = []
        if file_path:
            lines.append(f"Archivo: {file_path}")
        lines.append(f"Filas: {len(rows)}")
        lines.append(f"Columnas: {len(headers)}")
        lines.append(f"Nombres: {', '.join(headers)}")

        # Detectar tipos
        for h in headers:
            sample = [row.get(h, "") for row in rows[:100]]
            types = set()
            for v in sample:
                if v is None or str(v) == "":
                    types.add("null")
                else:
                    try:
                        float(v)
                        types.add("numeric")
                    except (ValueError, TypeError):
                        types.add("text")
            lines.append(f"  {h}: {', '.join(sorted(types))}")

        return ToolResult(success=True, output="\n".join(lines))
