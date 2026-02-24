"""
test_pr_reviewer.py — Tests para PrReviewerTool.

Verifica:
- Review basico de diff proporcionado directamente
- Manejo de diff vacio
- Review con AI (mock de client.generate)
- Deteccion de patrones problematicos (TODO, print, eval)
- Metadata del tool
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from mikalia.tools.pr_reviewer import PrReviewerTool
from mikalia.tools.base import ToolResult


# ================================================================
# Review basico (sin AI)
# ================================================================

class TestBasicReview:
    def test_basic_review_from_diff(self):
        """Review basico con diff text proporcionado."""
        tool = PrReviewerTool(client=None)

        diff = (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,3 +1,5 @@\n"
            "+import os\n"
            "+\n"
            " def main():\n"
            "-    pass\n"
            "+    print('hello')\n"
            "+    return True\n"
        )

        result = tool.execute(source="diff", diff_text=diff)
        assert result.success
        assert "Review basico" in result.output
        assert "Archivos:" in result.output
        assert "Lineas:" in result.output

    def test_empty_diff(self):
        """Diff vacio retorna error."""
        tool = PrReviewerTool(client=None)
        result = tool.execute(source="diff", diff_text="")
        assert not result.success
        assert "No hay cambios" in result.error


# ================================================================
# Deteccion de patrones
# ================================================================

class TestPatternDetection:
    def test_detects_todo_in_diff(self):
        """Detecta TODO/FIXME en lineas agregadas."""
        tool = PrReviewerTool(client=None)

        diff = (
            "diff --git a/module.py b/module.py\n"
            "+++ b/module.py\n"
            "+# TODO: fix this later\n"
            "+def broken():\n"
            "+    pass\n"
        )

        result = tool.execute(source="diff", diff_text=diff)
        assert result.success
        assert "TODO" in result.output

    def test_detects_print_statement(self):
        """Detecta print() en codigo de produccion."""
        tool = PrReviewerTool(client=None)

        diff = (
            "diff --git a/server.py b/server.py\n"
            "+++ b/server.py\n"
            "+def handler():\n"
            "+    print('debug output')\n"
            "+    return response\n"
        )

        result = tool.execute(source="diff", diff_text=diff)
        assert result.success
        assert "print()" in result.output

    def test_detects_eval(self):
        """Detecta eval/exec como riesgo de seguridad."""
        tool = PrReviewerTool(client=None)

        diff = (
            "diff --git a/utils.py b/utils.py\n"
            "+++ b/utils.py\n"
            "+result = eval(user_input)\n"
        )

        result = tool.execute(source="diff", diff_text=diff)
        assert result.success
        assert "eval" in result.output.lower()


# ================================================================
# AI review (mock)
# ================================================================

class TestAIReview:
    def test_ai_review_with_client(self):
        """Review con AI usa client.generate."""
        mock_client = MagicMock()
        mock_client.generate.return_value = (
            "El codigo se ve bien. Solo un detalle menor:\n"
            "- L5: Variable no usada (bajo)"
        )

        tool = PrReviewerTool(client=mock_client)

        diff = (
            "diff --git a/app.py b/app.py\n"
            "+++ b/app.py\n"
            "+def calculate(x, y):\n"
            "+    unused = 42\n"
            "+    return x + y\n"
        )

        result = tool.execute(source="diff", diff_text=diff, focus="general")
        assert result.success
        assert "Code Review" in result.output
        assert "Variable no usada" in result.output

        # Verificar que generate fue llamado
        mock_client.generate.assert_called_once()
        call_args = mock_client.generate.call_args
        assert call_args[1]["max_tokens"] == 1000
        assert call_args[1]["temperature"] == 0.3


# ================================================================
# Metadata
# ================================================================

class TestPrReviewerMetadata:
    def test_tool_metadata(self):
        """Metadata del tool es correcta."""
        tool = PrReviewerTool()
        assert tool.name == "pr_reviewer"
        assert "review" in tool.description.lower() or "Review" in tool.description

        defn = tool.to_claude_definition()
        assert defn["name"] == "pr_reviewer"
        assert "input_schema" in defn
        assert "source" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["properties"]["source"]["enum"] == [
            "staged", "branch", "diff"
        ]
        assert "source" in defn["input_schema"]["required"]
