"""
data_viz.py — Visualizacion de datos para Mikalia.

Genera graficas con matplotlib y las guarda como PNG.
Soporta: barras, lineas, pie, scatter, histograma.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.data_viz")

CHARTS_DIR = Path("data/charts")


class DataVisualizationTool(BaseTool):
    """Genera graficas y visualizaciones de datos."""

    @property
    def name(self) -> str:
        return "data_viz"

    @property
    def description(self) -> str:
        return (
            "Generate data visualizations as PNG images. "
            "Supports: bar, line, pie, scatter, histogram. "
            "Provide data as JSON arrays and specify chart type. "
            "Returns the file path of the generated chart."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "description": "Type of chart: bar, line, pie, scatter, histogram",
                    "enum": ["bar", "line", "pie", "scatter", "histogram"],
                },
                "data": {
                    "type": "string",
                    "description": (
                        'JSON data. For bar/line/pie: {"labels": [...], "values": [...]}. '
                        'For scatter: {"x": [...], "y": [...]}. '
                        'For histogram: {"values": [...]}'
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Chart title",
                },
                "xlabel": {
                    "type": "string",
                    "description": "X-axis label",
                },
                "ylabel": {
                    "type": "string",
                    "description": "Y-axis label",
                },
            },
            "required": ["chart_type", "data"],
        }

    def execute(
        self,
        chart_type: str,
        data: str,
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        **_: Any,
    ) -> ToolResult:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return ToolResult(
                success=False,
                error="matplotlib no instalado. Ejecuta: pip install matplotlib",
            )

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            return ToolResult(success=False, error=f"JSON invalido: {e}")

        try:
            fig, ax = plt.subplots(figsize=(10, 6))

            if chart_type == "bar":
                labels = parsed.get("labels", [])
                values = parsed.get("values", [])
                ax.bar(labels, values, color="#f0a500")

            elif chart_type == "line":
                labels = parsed.get("labels", [])
                values = parsed.get("values", [])
                ax.plot(labels, values, marker="o", color="#ff6b35", linewidth=2)

            elif chart_type == "pie":
                labels = parsed.get("labels", [])
                values = parsed.get("values", [])
                ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)

            elif chart_type == "scatter":
                x = parsed.get("x", [])
                y = parsed.get("y", [])
                ax.scatter(x, y, color="#f0a500", alpha=0.7)

            elif chart_type == "histogram":
                values = parsed.get("values", [])
                bins = parsed.get("bins", 10)
                ax.hist(values, bins=bins, color="#f0a500", edgecolor="black")

            if title:
                ax.set_title(title, fontsize=14, fontweight="bold")
            if xlabel:
                ax.set_xlabel(xlabel)
            if ylabel:
                ax.set_ylabel(ylabel)

            if chart_type != "pie":
                ax.grid(True, alpha=0.3)

            plt.tight_layout()

            CHARTS_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"chart_{int(time.time())}.png"
            filepath = CHARTS_DIR / filename
            fig.savefig(filepath, dpi=150, bbox_inches="tight")
            plt.close(fig)

            logger.success(f"Chart generado: {filepath}")
            return ToolResult(
                success=True,
                output=f"Chart guardado en: {filepath}\nTipo: {chart_type}\nTitulo: {title or '(sin titulo)'}",
            )

        except Exception as e:
            plt.close("all")
            return ToolResult(success=False, error=f"Error generando chart: {e}")
