"""
pr_reviewer.py — Auto-reviewer de Pull Requests para Mikalia.

Lee diffs de PRs y genera code reviews usando Claude.
Integra con las herramientas de GitHub existentes.
"""

from __future__ import annotations

import subprocess
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.pr_reviewer")

MAX_DIFF_LENGTH = 20000


class PrReviewerTool(BaseTool):
    """Auto-review de Pull Requests con AI."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "pr_reviewer"

    @property
    def description(self) -> str:
        return (
            "Auto-review a Git Pull Request or diff. "
            "Analyzes code changes for: bugs, security issues, "
            "style problems, and improvement suggestions. "
            "Can review a local diff or a GitHub PR by number."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Source: 'staged' (git diff --staged), 'branch' (vs main), or 'diff' (raw diff)",
                    "enum": ["staged", "branch", "diff"],
                },
                "diff_text": {
                    "type": "string",
                    "description": "Raw diff text (only if source='diff')",
                },
                "base_branch": {
                    "type": "string",
                    "description": "Base branch for comparison (default: main)",
                },
                "focus": {
                    "type": "string",
                    "description": "Review focus: general, security, performance, style",
                },
            },
            "required": ["source"],
        }

    def execute(
        self,
        source: str,
        diff_text: str = "",
        base_branch: str = "main",
        focus: str = "general",
        **_: Any,
    ) -> ToolResult:
        # Obtener diff
        diff = self._get_diff(source, diff_text, base_branch)
        if not diff:
            return ToolResult(success=False, error="No hay cambios para revisar")

        if len(diff) > MAX_DIFF_LENGTH:
            diff = diff[:MAX_DIFF_LENGTH] + "\n...[diff truncado]"

        # Generar review
        if self._client:
            return self._ai_review(diff, focus)
        else:
            return self._basic_review(diff)

    def _get_diff(self, source: str, diff_text: str, base_branch: str) -> str:
        """Obtiene el diff segun la fuente."""
        if source == "diff":
            return diff_text

        try:
            if source == "staged":
                cmd = ["git", "diff", "--staged"]
            else:  # branch
                cmd = ["git", "diff", f"{base_branch}...HEAD"]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10
            )
            return result.stdout
        except Exception as e:
            logger.warning(f"Error obteniendo diff: {e}")
            return ""

    def _ai_review(self, diff: str, focus: str) -> ToolResult:
        """Review usando Claude."""
        focus_prompts = {
            "general": "bugs, seguridad, estilo, y mejoras generales",
            "security": "vulnerabilidades de seguridad, inyeccion, XSS, secrets expuestos",
            "performance": "problemas de rendimiento, N+1 queries, memory leaks, algoritmos ineficientes",
            "style": "convenciones de estilo, naming, estructura, legibilidad",
        }

        focus_desc = focus_prompts.get(focus, focus_prompts["general"])

        prompt = (
            f"Revisa el siguiente diff de codigo enfocandote en: {focus_desc}.\n\n"
            "Para cada issue encontrado, indica:\n"
            "- Archivo y linea aproximada\n"
            "- Severidad (critico/alto/medio/bajo)\n"
            "- Descripcion del problema\n"
            "- Sugerencia de solucion\n\n"
            "Si el codigo se ve bien, dilo tambien.\n"
            "Responde en español.\n\n"
            f"```diff\n{diff}\n```"
        )

        try:
            response = self._client.generate(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3,
            )
            logger.success("PR review generado con AI")
            return ToolResult(
                success=True,
                output=f"=== Code Review ({focus}) ===\n\n{response}",
            )
        except Exception as e:
            logger.warning(f"AI review failed: {e}")
            return self._basic_review(diff)

    def _basic_review(self, diff: str) -> ToolResult:
        """Review basico sin AI: busca patrones comunes."""
        issues = []

        lines = diff.split("\n")
        for i, line in enumerate(lines):
            if not line.startswith("+"):
                continue

            # Patterns problematicos
            if "TODO" in line or "FIXME" in line or "HACK" in line:
                issues.append(f"  L{i}: TODO/FIXME encontrado")
            if "password" in line.lower() and "=" in line:
                issues.append(f"  L{i}: Posible password hardcodeado")
            if "print(" in line and "test" not in line.lower():
                issues.append(f"  L{i}: print() en codigo de produccion")
            if "import *" in line:
                issues.append(f"  L{i}: import * (wildcard import)")
            if "eval(" in line or "exec(" in line:
                issues.append(f"  L{i}: eval/exec detectado (riesgo de seguridad)")

        # Stats del diff
        added = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
        removed = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
        files = [ln.split(" b/")[-1] for ln in lines if ln.startswith("diff --git")]

        output = [
            "=== Review basico ===",
            f"Archivos: {len(files)}",
            f"Lineas: +{added} / -{removed}",
        ]

        if issues:
            output.append(f"\nIssues encontrados ({len(issues)}):")
            output.extend(issues[:20])
        else:
            output.append("\nNo se detectaron problemas obvios.")

        return ToolResult(success=True, output="\n".join(output))
