"""
test_data_viz.py — Tests para DataVisualizationTool.

Verifica:
- Generacion de graficas (bar, line, pie, scatter, histogram)
- Manejo de JSON invalido
- Manejo de matplotlib no instalado
- Definiciones Claude correctas
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mikalia.tools.data_viz import DataVisualizationTool


# ================================================================
# Helpers
# ================================================================

def _make_mock_plt():
    """Crea mocks de matplotlib.pyplot, figure y axes."""
    mock_plt = MagicMock()
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)
    return mock_plt, mock_fig, mock_ax


def _matplotlib_modules(mock_plt):
    """Construye un dict que reemplaza todos los modulos de matplotlib en sys.modules.

    patch.dict solo *agrega/sobreescribe* claves pero no elimina las que ya
    esten en sys.modules.  Para que ``import matplotlib.pyplot as plt`` dentro
    de execute() apunte a nuestro mock, necesitamos asegurarnos de que no haya
    ninguna entrada previa de matplotlib.
    """
    mock_mpl = MagicMock()
    mock_mpl.pyplot = mock_plt

    # Recopilar claves existentes de matplotlib para forzar su sobreescritura
    existing = {k: MagicMock() for k in list(sys.modules) if k.startswith("matplotlib")}
    existing["matplotlib"] = mock_mpl
    existing["matplotlib.pyplot"] = mock_plt
    return existing


# ================================================================
# DataVisualizationTool — chart generation
# ================================================================

class TestDataVisualizationCharts:
    def test_bar_chart(self, tmp_path):
        """Genera un bar chart correctamente."""
        mock_plt, mock_fig, mock_ax = _make_mock_plt()

        with patch.dict("sys.modules", _matplotlib_modules(mock_plt)):
            with patch("mikalia.tools.data_viz.CHARTS_DIR", tmp_path):
                tool = DataVisualizationTool()
                data = json.dumps({"labels": ["A", "B", "C"], "values": [10, 20, 30]})
                result = tool.execute(chart_type="bar", data=data, title="Test Bar")

        assert result.success
        assert "bar" in result.output.lower()
        mock_ax.bar.assert_called_once()
        mock_fig.savefig.assert_called_once()

    def test_line_chart(self, tmp_path):
        """Genera un line chart correctamente."""
        mock_plt, mock_fig, mock_ax = _make_mock_plt()

        with patch.dict("sys.modules", _matplotlib_modules(mock_plt)):
            with patch("mikalia.tools.data_viz.CHARTS_DIR", tmp_path):
                tool = DataVisualizationTool()
                data = json.dumps({"labels": ["Jan", "Feb", "Mar"], "values": [5, 15, 25]})
                result = tool.execute(chart_type="line", data=data, title="Test Line")

        assert result.success
        assert "line" in result.output.lower()
        mock_ax.plot.assert_called_once()

    def test_pie_chart(self, tmp_path):
        """Genera un pie chart correctamente."""
        mock_plt, mock_fig, mock_ax = _make_mock_plt()

        with patch.dict("sys.modules", _matplotlib_modules(mock_plt)):
            with patch("mikalia.tools.data_viz.CHARTS_DIR", tmp_path):
                tool = DataVisualizationTool()
                data = json.dumps({"labels": ["X", "Y", "Z"], "values": [40, 35, 25]})
                result = tool.execute(chart_type="pie", data=data)

        assert result.success
        assert "pie" in result.output.lower()
        mock_ax.pie.assert_called_once()
        # Pie charts no tienen grid
        mock_ax.grid.assert_not_called()

    def test_scatter_chart(self, tmp_path):
        """Genera un scatter chart correctamente."""
        mock_plt, mock_fig, mock_ax = _make_mock_plt()

        with patch.dict("sys.modules", _matplotlib_modules(mock_plt)):
            with patch("mikalia.tools.data_viz.CHARTS_DIR", tmp_path):
                tool = DataVisualizationTool()
                data = json.dumps({"x": [1, 2, 3, 4], "y": [10, 20, 15, 25]})
                result = tool.execute(
                    chart_type="scatter", data=data,
                    title="Scatter", xlabel="X", ylabel="Y",
                )

        assert result.success
        assert "scatter" in result.output.lower()
        mock_ax.scatter.assert_called_once()
        mock_ax.set_xlabel.assert_called_with("X")
        mock_ax.set_ylabel.assert_called_with("Y")

    def test_histogram(self, tmp_path):
        """Genera un histogram correctamente."""
        mock_plt, mock_fig, mock_ax = _make_mock_plt()

        with patch.dict("sys.modules", _matplotlib_modules(mock_plt)):
            with patch("mikalia.tools.data_viz.CHARTS_DIR", tmp_path):
                tool = DataVisualizationTool()
                data = json.dumps({"values": [1, 2, 2, 3, 3, 3, 4, 4, 5]})
                result = tool.execute(chart_type="histogram", data=data)

        assert result.success
        assert "histogram" in result.output.lower()
        mock_ax.hist.assert_called_once()


# ================================================================
# DataVisualizationTool — error handling
# ================================================================

class TestDataVisualizationErrors:
    def test_invalid_json(self):
        """JSON invalido retorna error."""
        mock_plt, _, _ = _make_mock_plt()

        with patch.dict("sys.modules", _matplotlib_modules(mock_plt)):
            tool = DataVisualizationTool()
            result = tool.execute(chart_type="bar", data="not valid json {{{")

        assert not result.success
        assert "JSON invalido" in result.error

    def test_matplotlib_not_installed(self):
        """Sin matplotlib retorna error descriptivo."""
        # Reemplazar con None fuerza un ImportError al hacer import
        mods = {k: None for k in list(sys.modules) if k.startswith("matplotlib")}
        mods["matplotlib"] = None
        mods["matplotlib.pyplot"] = None

        with patch.dict("sys.modules", mods):
            tool = DataVisualizationTool()
            result = tool.execute(
                chart_type="bar",
                data=json.dumps({"labels": ["A"], "values": [1]}),
            )

        assert not result.success
        assert "matplotlib" in result.error.lower()


# ================================================================
# DataVisualizationTool — metadata
# ================================================================

class TestDataVisualizationMetadata:
    def test_tool_metadata(self):
        """Definicion Claude tiene el formato correcto."""
        tool = DataVisualizationTool()
        assert tool.name == "data_viz"
        assert "visualization" in tool.description.lower()

        d = tool.to_claude_definition()
        assert d["name"] == "data_viz"
        assert "chart_type" in d["input_schema"]["properties"]
        assert "data" in d["input_schema"]["properties"]
        assert "chart_type" in d["input_schema"]["required"]
        assert "data" in d["input_schema"]["required"]
