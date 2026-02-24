"""
multi_model.py — Routing multi-modelo para Mikalia.

Permite enrutar consultas a diferentes modelos de Claude
segun complejidad, costo, o preferencia del usuario.
"""

from __future__ import annotations

from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.multi_model")

# Modelos disponibles con sus caracteristicas
MODELS = {
    "haiku": {
        "id": "claude-haiku-4-5-20251001",
        "name": "Claude 4.5 Haiku",
        "speed": "ultra-rapido",
        "cost": "bajo",
        "best_for": "tareas simples, clasificacion, extraccion, chat casual",
    },
    "sonnet": {
        "id": "claude-sonnet-4-5-20250929",
        "name": "Claude 4.5 Sonnet",
        "speed": "rapido",
        "cost": "medio",
        "best_for": "tareas generales, codigo, analisis, escritura",
    },
    "opus": {
        "id": "claude-opus-4-6",
        "name": "Claude Opus 4.6",
        "speed": "moderado",
        "cost": "alto",
        "best_for": "tareas complejas, razonamiento profundo, creatividad avanzada",
    },
}

# Reglas de auto-routing
COMPLEXITY_KEYWORDS = {
    "simple": ["traduce", "resume", "lista", "cuenta", "calcula", "define"],
    "medium": ["analiza", "compara", "explica", "genera", "escribe", "implementa"],
    "complex": ["diseña", "arquitectura", "optimiza", "refactoriza", "investiga"],
}


class MultiModelTool(BaseTool):
    """Enruta consultas a diferentes modelos Claude."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "multi_model"

    @property
    def description(self) -> str:
        return (
            "Route queries to different Claude models. Actions: "
            "query (send to specific model), "
            "auto (auto-select best model for the task), "
            "compare (run same prompt on multiple models), "
            "models (list available models). "
            "Useful for optimizing cost/quality tradeoffs."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: query, auto, compare, models",
                    "enum": ["query", "auto", "compare", "models"],
                },
                "prompt": {
                    "type": "string",
                    "description": "The prompt/question to send",
                },
                "model": {
                    "type": "string",
                    "description": "Model to use: haiku, sonnet, opus",
                    "enum": ["haiku", "sonnet", "opus"],
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Max tokens for response (default: 500)",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        prompt: str = "",
        model: str = "sonnet",
        max_tokens: int = 500,
        **_: Any,
    ) -> ToolResult:
        if action == "models":
            return self._list_models()

        if not self._client:
            return ToolResult(
                success=False,
                error="Multi-model necesita MikaliaClient para funcionar",
            )

        if not prompt:
            return ToolResult(success=False, error="Prompt requerido")

        if action == "query":
            return self._query(prompt, model, max_tokens)
        elif action == "auto":
            return self._auto_route(prompt, max_tokens)
        elif action == "compare":
            return self._compare(prompt, max_tokens)
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _list_models(self) -> ToolResult:
        lines = ["=== Modelos disponibles ==="]
        for key, info in MODELS.items():
            lines.append(
                f"\n{info['name']} ({key}):\n"
                f"  ID: {info['id']}\n"
                f"  Velocidad: {info['speed']}\n"
                f"  Costo: {info['cost']}\n"
                f"  Mejor para: {info['best_for']}"
            )
        return ToolResult(success=True, output="\n".join(lines))

    def _query(self, prompt: str, model_key: str, max_tokens: int) -> ToolResult:
        """Envia query a un modelo especifico."""
        model_info = MODELS.get(model_key)
        if not model_info:
            return ToolResult(success=False, error=f"Modelo desconocido: {model_key}")

        try:
            response = self._client.generate(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.7,
                model=model_info["id"],
            )

            return ToolResult(
                success=True,
                output=(
                    f"Modelo: {model_info['name']}\n"
                    f"---\n{response}"
                ),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Error con {model_key}: {e}")

    def _auto_route(self, prompt: str, max_tokens: int) -> ToolResult:
        """Selecciona automaticamente el mejor modelo."""
        prompt_lower = prompt.lower()

        # Detectar complejidad
        selected = "sonnet"  # default

        for keyword in COMPLEXITY_KEYWORDS["simple"]:
            if keyword in prompt_lower:
                selected = "haiku"
                break

        for keyword in COMPLEXITY_KEYWORDS["complex"]:
            if keyword in prompt_lower:
                selected = "opus"
                break

        # Longitud del prompt como factor
        if len(prompt) > 2000:
            selected = "opus" if selected != "haiku" else "sonnet"

        logger.info(f"Auto-routing a {selected}")
        result = self._query(prompt, selected, max_tokens)

        if result.success:
            result.output = f"[Auto-seleccionado: {selected}]\n\n{result.output}"

        return result

    def _compare(self, prompt: str, max_tokens: int) -> ToolResult:
        """Compara respuestas de haiku y sonnet."""
        results = []
        for model_key in ["haiku", "sonnet"]:
            result = self._query(prompt, model_key, max_tokens)
            if result.success:
                results.append(f"=== {MODELS[model_key]['name']} ===\n{result.output}")
            else:
                results.append(f"=== {model_key} === Error: {result.error}")

        return ToolResult(
            success=True,
            output="\n\n".join(results),
        )
