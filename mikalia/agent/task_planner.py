"""
task_planner.py — El cerebro estratégico de Mikalia.

Recibe una tarea en lenguaje natural y la descompone en
pasos concretos que el code_agent puede ejecutar.

Ejemplo:
    Input: "Add error handling to all API calls"
    Output:
        1. Scan for all files with API calls
        2. Identify unhandled exceptions
        3. Add try/catch with specific error types
        4. Add logging for each error
        5. Update tests if they exist

También clasifica la tarea:
    - POST → Va al post_generator
    - FIX  → Bug fix, prioridad alta
    - FEAT → Feature nueva
    - DOCS → Documentación
    - SECURITY → Alerta especial a Mikata-kun

Usa Claude API con system prompt de "arquitecto de software"
para generar planes de alta calidad.

Uso:
    from mikalia.agent.task_planner import TaskPlanner
    planner = TaskPlanner(client)
    plan = planner.plan("Add error handling to API calls", repo_context)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from mikalia.generation.client import MikaliaClient
from mikalia.generation.repo_analyzer import RepoContext
from mikalia.agent.safety import SafetyGuard, SafetyResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.task_planner")


class TaskType(Enum):
    """
    Tipos de tarea que Mikalia puede ejecutar.

    Cada tipo tiene un flujo diferente:
    - POST: Va al post_generator (F1/F2)
    - FIX: Bug fix, prioridad alta, branch mikalia/fix/
    - FEAT: Feature nueva, branch mikalia/feat/
    - DOCS: Documentación, branch mikalia/docs/
    - SECURITY: Alerta especial, requiere aprobación inmediata
    """
    POST = "post"
    FIX = "fix"
    FEAT = "feat"
    DOCS = "docs"
    SECURITY = "security"


class ComplexityLevel(Enum):
    """
    Niveles de complejidad estimada de una tarea.

    LOW:         1-3 archivos, cambios simples
    MEDIUM:      3-7 archivos, lógica nueva
    HIGH:        7+ archivos, refactor significativo
    NEEDS_HUMAN: Demasiado complejo o riesgoso para autonomía
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NEEDS_HUMAN = "needs_human"


@dataclass
class Step:
    """
    Un paso individual dentro de un plan de tarea.

    Campos:
        number: Número de paso (1, 2, 3...)
        description: Qué hacer en este paso
        files: Archivos que se tocarán en este paso
        action: Tipo de acción (modify, create, delete)
    """
    number: int
    description: str
    files: list[str] = field(default_factory=list)
    action: str = "modify"  # modify, create, delete


@dataclass
class TaskPlan:
    """
    Plan completo para una tarea.

    Contiene la clasificación, pasos a seguir, estimación
    de complejidad, y resultado de verificación de seguridad.

    Campos:
        task_description: Descripción original de la tarea
        task_type: Tipo de tarea (fix, feat, docs, etc.)
        steps: Lista ordenada de pasos a ejecutar
        complexity: Nivel de complejidad estimado
        safety_check: Resultado de la verificación de seguridad
        branch_name: Nombre sugerido del branch
        estimated_files: Número estimado de archivos a modificar
        estimated_lines: Número estimado de líneas a cambiar
    """
    task_description: str
    task_type: TaskType
    steps: list[Step] = field(default_factory=list)
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM
    safety_check: SafetyResult | None = None
    branch_name: str = ""
    estimated_files: int = 0
    estimated_lines: int = 0

    @property
    def is_safe(self) -> bool:
        """Verifica si el plan pasó la verificación de seguridad."""
        return self.safety_check is not None and self.safety_check.allowed

    @property
    def files_to_modify(self) -> list[str]:
        """Lista consolidada de archivos a modificar."""
        archivos = []
        for step in self.steps:
            for f in step.files:
                if f not in archivos:
                    archivos.append(f)
        return archivos


class TaskPlanner:
    """
    Planificador de tareas para el agente de código.

    Recibe una tarea en lenguaje natural, la clasifica,
    descompone en pasos, estima complejidad, y verifica
    seguridad antes de pasarla al code_agent.

    Args:
        client: Cliente de la API de Claude
        safety_guard: Guardián de seguridad
    """

    # Prompt para Claude como arquitecto de software
    PLANNER_PROMPT = """You are a senior software architect planning code changes.

Given a task description and repository context, create a detailed plan.

Task: {task}

Repository context:
{context}

Respond in JSON format:
{{
    "task_type": "fix|feat|docs|security",
    "steps": [
        {{
            "number": 1,
            "description": "What to do",
            "files": ["path/to/file.py"],
            "action": "modify|create|delete"
        }}
    ],
    "complexity": "low|medium|high|needs_human",
    "estimated_files": 3,
    "estimated_lines": 100,
    "branch_slug": "descriptive-slug"
}}

Rules:
- Keep changes minimal and focused
- Never suggest modifying .env, secrets, or workflow files
- Prefer modifying existing files over creating new ones
- Include tests if the repo has a test directory
- Respond ONLY with valid JSON, no markdown fences"""

    def __init__(
        self,
        client: MikaliaClient,
        safety_guard: SafetyGuard | None = None,
    ):
        self._client = client
        self._safety = safety_guard or SafetyGuard()

    def plan(
        self,
        task_description: str,
        repo_context: RepoContext | None = None,
    ) -> TaskPlan:
        """
        Planifica una tarea completa.

        Flujo:
        1. Clasifica la tarea (fix, feat, docs, etc.)
        2. Genera un plan con pasos específicos
        3. Estima complejidad
        4. Verifica seguridad de cada paso
        5. Retorna el plan listo para ejecutar

        Args:
            task_description: Descripción en lenguaje natural.
            repo_context: Contexto del repositorio (de repo_analyzer).

        Returns:
            TaskPlan con todos los detalles.
        """
        logger.info(f"Planificando tarea: {task_description}")

        # Generar plan con Claude
        context_str = repo_context.to_prompt(max_tokens=4000) if repo_context else "No repository context available."

        prompt = self.PLANNER_PROMPT.format(
            task=task_description,
            context=context_str,
        )

        respuesta = self._client.generate(
            user_prompt=prompt,
            temperature=0.3,  # Baja para planificación precisa
            max_tokens=2048,
            system_override=(
                "You are a precise task planning engine. "
                "You ALWAYS respond with valid JSON only. "
                "No markdown fences, no explanations outside JSON."
            ),
        )

        # Parsear el plan
        plan = self._parse_plan(respuesta.content, task_description)

        # Verificar seguridad
        logger.info("Verificando seguridad del plan...")
        plan.safety_check = self._safety.validate_task(
            files_to_modify=plan.files_to_modify,
            target_branch=plan.branch_name,
            total_lines=plan.estimated_lines,
        )

        if plan.is_safe:
            logger.success(
                f"Plan aprobado: {len(plan.steps)} pasos, "
                f"{plan.estimated_files} archivos, "
                f"complejidad: {plan.complexity.value}"
            )
        else:
            logger.warning(
                f"Plan bloqueado por seguridad: {plan.safety_check.reason}"
            )

        return plan

    def _parse_plan(self, response: str, task_description: str) -> TaskPlan:
        """
        Parsea la respuesta de Claude a un TaskPlan.

        Maneja errores de parseo con defaults seguros.

        Args:
            response: Respuesta JSON de Claude.
            task_description: Descripción original.

        Returns:
            TaskPlan parseado.
        """
        try:
            # Limpiar code fences si las hay
            texto = response.strip()
            if texto.startswith("```"):
                texto = texto.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            datos = json.loads(texto)
        except json.JSONDecodeError:
            logger.warning("No se pudo parsear plan JSON, usando defaults")
            return TaskPlan(
                task_description=task_description,
                task_type=TaskType.FEAT,
                complexity=ComplexityLevel.NEEDS_HUMAN,
                branch_name="mikalia/feat/unparsed-task",
            )

        # Extraer tipo de tarea
        tipo_str = datos.get("task_type", "feat")
        try:
            task_type = TaskType(tipo_str)
        except ValueError:
            task_type = TaskType.FEAT

        # Extraer pasos
        steps = []
        for step_data in datos.get("steps", []):
            steps.append(Step(
                number=step_data.get("number", len(steps) + 1),
                description=step_data.get("description", ""),
                files=step_data.get("files", []),
                action=step_data.get("action", "modify"),
            ))

        # Extraer complejidad
        complexity_str = datos.get("complexity", "medium")
        try:
            complexity = ComplexityLevel(complexity_str)
        except ValueError:
            complexity = ComplexityLevel.MEDIUM

        # Generar nombre de branch
        slug = datos.get("branch_slug", "task")
        branch_name = f"mikalia/{task_type.value}/{slug}"

        return TaskPlan(
            task_description=task_description,
            task_type=task_type,
            steps=steps,
            complexity=complexity,
            branch_name=branch_name,
            estimated_files=datos.get("estimated_files", len(steps)),
            estimated_lines=datos.get("estimated_lines", 0),
        )

    def classify_task(self, description: str) -> TaskType:
        """
        Clasificación rápida de una tarea sin usar la API.

        Usa heurísticas simples basadas en keywords para
        clasificar la tarea sin gastar tokens de API.

        Args:
            description: Descripción de la tarea.

        Returns:
            TaskType inferido.
        """
        desc_lower = description.lower()

        # Keywords para cada tipo
        fix_keywords = ["fix", "bug", "error", "crash", "broken", "issue", "patch"]
        docs_keywords = ["readme", "docs", "documentation", "comment", "docstring", "typo"]
        security_keywords = ["security", "vulnerability", "CVE", "injection", "XSS", "auth"]
        post_keywords = ["post", "blog", "article", "write about"]

        if any(kw in desc_lower for kw in security_keywords):
            return TaskType.SECURITY
        if any(kw in desc_lower for kw in fix_keywords):
            return TaskType.FIX
        if any(kw in desc_lower for kw in docs_keywords):
            return TaskType.DOCS
        if any(kw in desc_lower for kw in post_keywords):
            return TaskType.POST

        return TaskType.FEAT
