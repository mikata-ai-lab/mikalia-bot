"""
code_agent.py — El modo más avanzado de Mikalia: agente de código.

Aquí Mikalia puede analizar código, proponer cambios, y crear PRs.
Es la culminación de F1 (genera contenido) + F2 (lee repos) +
la capacidad nueva de MODIFICAR código.

Flujo:
    1. Recibe tarea (ej: "Fix bug in X", "Add feature Y")
    2. Analiza el repo relevante (usa repo_analyzer de F2)
    3. Planifica los cambios necesarios (task_planner)
    4. Genera los cambios de código
    5. Valida los cambios con SafetyGuard
    6. Crea branch + commit + PR
    7. Comenta en el PR explicando cada cambio
    8. Notifica por Telegram

IMPORTANTE — Guardrails de seguridad:
    - NUNCA modifica archivos .env o secrets
    - NUNCA pushea directo a main (siempre PR)
    - NUNCA ejecuta código generado automáticamente
    - Máximo N archivos por PR (configurable)
    - Siempre requiere aprobación humana (Mikata-kun)

Uso:
    from mikalia.agent.code_agent import CodeAgent
    agent = CodeAgent(client, config)
    result = agent.execute_task(
        repo="mikata-ai-lab/mikalia-bot",
        task="Add error handling to all API calls"
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from mikalia.config import AppConfig
from mikalia.generation.client import MikaliaClient
from mikalia.generation.repo_analyzer import RepoAnalyzer, RepoContext
from mikalia.agent.safety import SafetyGuard, SafetyResult, Severity
from mikalia.agent.task_planner import TaskPlanner, TaskPlan
from mikalia.publishing.pr_manager import PRManager, PullRequest
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.code_agent")


@dataclass
class CodeChange:
    """
    Un cambio de código propuesto por Mikalia.

    Campos:
        file: Ruta relativa del archivo
        action: "modify", "create", o "delete"
        original: Contenido original (si modify)
        modified: Contenido nuevo
        explanation: Explicación del cambio en español
    """
    file: str
    action: str = "modify"
    original: str = ""
    modified: str = ""
    explanation: str = ""

    @property
    def lines_changed(self) -> int:
        """Estimación de líneas cambiadas."""
        if self.action == "create":
            return len(self.modified.splitlines())
        elif self.action == "delete":
            return len(self.original.splitlines())
        else:
            # Diferencia aproximada
            orig_lines = set(self.original.splitlines())
            mod_lines = set(self.modified.splitlines())
            return len(orig_lines.symmetric_difference(mod_lines))


@dataclass
class AgentResult:
    """
    Resultado de la ejecución del agente de código.

    Campos:
        success: Si la tarea se completó exitosamente
        pr: Pull Request creado (si success)
        changes: Lista de cambios realizados
        plan: Plan que se ejecutó
        summary: Resumen de lo que se hizo
        error: Mensaje de error (si falló)
    """
    success: bool = False
    pr: PullRequest | None = None
    changes: list[CodeChange] = field(default_factory=list)
    plan: TaskPlan | None = None
    summary: str = ""
    error: str = ""


class CodeAgent:
    """
    Agente de código autónomo de Mikalia.

    Orquesta todo el flujo: análisis → planificación →
    generación de código → validación → PR.

    Args:
        client: Cliente de la API de Claude.
        config: Configuración de la app.
        safety_guard: Guardián de seguridad.
    """

    # Prompt para generar cambios de código
    CODE_CHANGE_PROMPT = """You are a senior software engineer implementing code changes.

Task: {task}
Plan step: {step_description}
File to modify: {file_path}

Current file content:
```
{file_content}
```

Repository context:
{repo_context}

Instructions:
1. Implement the change described in the plan step
2. Maintain the existing code style (comments in Spanish)
3. Make MINIMAL changes — only what's needed
4. Do NOT remove existing comments or docstrings
5. Ensure the code is correct and complete

Respond in JSON with a list of search/replace edits:
{{
    "edits": [
        {{
            "search": "... (exact text to find in the file)",
            "replace": "... (replacement text)"
        }}
    ],
    "explanation": "... (explanation of what was changed and why, in Spanish)"
}}

Each edit replaces one occurrence. Use enough surrounding context in "search" to be unique.
IMPORTANT: Respond ONLY with valid JSON, no markdown fences."""

    CREATE_FILE_PROMPT = """You are a senior software engineer creating a new file.

Task: {task}
Plan step: {step_description}
File to create: {file_path}

Repository context:
{repo_context}

Instructions:
1. Create the file content as specified in the plan
2. Follow the project's code style (comments in Spanish, type hints)
3. Include docstrings explaining what the file does and why
4. Make it consistent with existing code patterns

Respond in JSON format:
{{
    "file_content": "... (complete file content)",
    "explanation": "... (explanation of the new file, in Spanish)"
}}

IMPORTANT: Respond ONLY with valid JSON, no markdown fences."""

    # System prompt para el agente de código (reemplaza a MIKALIA.md)
    AGENT_SYSTEM = (
        "You are a precise code generation engine. "
        "You ALWAYS respond with valid JSON only. "
        "No markdown fences, no explanations outside JSON, no preamble."
    )

    def __init__(
        self,
        client: MikaliaClient,
        config: AppConfig,
        safety_guard: SafetyGuard | None = None,
    ):
        self._client = client
        self._config = config
        self._safety = safety_guard or SafetyGuard()
        self._planner = TaskPlanner(client, self._safety)
        self._repo_analyzer = RepoAnalyzer()

    def execute_task(
        self,
        repo: str,
        task: str,
        dry_run: bool = False,
    ) -> AgentResult:
        """
        Ejecuta una tarea de código completa.

        Este es el método principal que orquesta todo el flujo
        del agente. Desde análisis hasta la creación del PR.

        Args:
            repo: Identificador del repo (local path o "owner/repo").
            task: Descripción de la tarea en lenguaje natural.
            dry_run: Si True, genera cambios pero no crea PR.

        Returns:
            AgentResult con el resultado de la ejecución.
        """
        logger.mikalia(f"Modo agente activado: {task}")

        try:
            # === PASO 1: Analizar repo ===
            logger.step(1, 6, "Analizando repositorio...")
            repo_context = self._repo_analyzer.analyze(repo, focus_topic=task)

            # === PASO 2: Planificar ===
            logger.step(2, 6, "Planificando cambios...")
            plan = self._planner.plan(task, repo_context)

            if not plan.is_safe:
                return AgentResult(
                    success=False,
                    plan=plan,
                    error=f"Plan bloqueado por seguridad: {plan.safety_check.reason}",
                )

            if plan.complexity.value == "needs_human":
                return AgentResult(
                    success=False,
                    plan=plan,
                    error="Tarea demasiado compleja para autonomía. Requiere intervención humana.",
                )

            # === PASO 3: Generar cambios ===
            logger.step(3, 6, "Generando cambios de código...")
            changes = self._generate_changes(plan, repo, repo_context)

            if not changes:
                return AgentResult(
                    success=False,
                    plan=plan,
                    error="No se pudieron generar cambios de código.",
                )

            # === PASO 4: Validar cambios ===
            logger.step(4, 6, "Validando cambios...")
            validation = self._validate_changes(changes)
            if not validation.allowed:
                return AgentResult(
                    success=False,
                    plan=plan,
                    changes=changes,
                    error=f"Cambios bloqueados: {validation.reason}",
                )

            # === PASO 5: Dry run o crear PR ===
            if dry_run:
                logger.step(5, 6, "Dry run — mostrando cambios...")
                return AgentResult(
                    success=True,
                    plan=plan,
                    changes=changes,
                    summary=self._generate_summary(task, changes),
                )

            # === PASO 5: Crear PR ===
            logger.step(5, 6, "Creando Pull Request...")
            pr = self._create_pr(repo, plan, changes, task)

            # === PASO 6: Resultado ===
            logger.step(6, 6, "Completado")
            summary = self._generate_summary(task, changes)

            if pr and pr.number > 0:
                logger.success(f"PR #{pr.number} creado: {pr.url}")
            else:
                logger.warning("PR no se pudo crear, pero los cambios están listos")

            return AgentResult(
                success=True,
                pr=pr,
                plan=plan,
                changes=changes,
                summary=summary,
            )

        except Exception as e:
            logger.error(f"Error en agente: {e}")
            return AgentResult(
                success=False,
                error=str(e),
            )

    def _generate_changes(
        self,
        plan: TaskPlan,
        repo: str,
        repo_context: RepoContext,
    ) -> list[CodeChange]:
        """
        Genera los cambios de código para cada paso del plan.

        Por cada archivo en el plan, hace una llamada a Claude
        para generar el código modificado.

        Args:
            plan: Plan de la tarea.
            repo: Identificador del repo.
            repo_context: Contexto del repo.

        Returns:
            Lista de cambios generados.
        """
        changes = []
        repo_path = self._repo_analyzer._resolve_repo_path(repo)
        context_str = repo_context.to_prompt(max_tokens=3000)

        for step in plan.steps:
            for file_path in step.files:
                # Verificar seguridad del archivo
                safety_check = self._safety.check_file_access(file_path)
                if not safety_check.allowed:
                    logger.warning(f"Archivo bloqueado, saltando: {file_path}")
                    continue

                full_path = repo_path / file_path

                if step.action == "create" or not full_path.exists():
                    # Crear archivo nuevo
                    change = self._generate_new_file(
                        plan.task_description, step.description,
                        file_path, context_str,
                    )
                elif step.action == "delete":
                    # Borrar archivo (solo proponer, no ejecutar)
                    original = self._safe_read(full_path)
                    change = CodeChange(
                        file=file_path,
                        action="delete",
                        original=original,
                        explanation=f"Archivo a eliminar: {step.description}",
                    )
                else:
                    # Modificar archivo existente
                    original = self._safe_read(full_path)
                    change = self._generate_modification(
                        plan.task_description, step.description,
                        file_path, original, context_str,
                    )

                if change:
                    changes.append(change)

        return changes

    def _generate_modification(
        self,
        task: str,
        step_description: str,
        file_path: str,
        file_content: str,
        repo_context: str,
    ) -> CodeChange | None:
        """
        Genera una modificación para un archivo existente.

        Args:
            task: Descripción de la tarea.
            step_description: Descripción del paso actual.
            file_path: Ruta del archivo.
            file_content: Contenido actual del archivo.
            repo_context: Contexto del repositorio.

        Returns:
            CodeChange con la modificación, o None si falla.
        """
        prompt = self.CODE_CHANGE_PROMPT.format(
            task=task,
            step_description=step_description,
            file_path=file_path,
            file_content=file_content[:8000],  # Truncar si es muy largo
            repo_context=repo_context,
        )

        try:
            respuesta = self._client.generate(
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=4096,
                system_override=self.AGENT_SYSTEM,
            )

            datos = self._parse_json_response(respuesta.content)
            if not datos:
                return None

            # Aplicar edits de search/replace al contenido original
            modified = file_content
            edits = datos.get("edits", [])
            for edit in edits:
                search = edit.get("search", "")
                replace = edit.get("replace", "")
                if search and search in modified:
                    modified = modified.replace(search, replace, 1)

            return CodeChange(
                file=file_path,
                action="modify",
                original=file_content,
                modified=modified,
                explanation=datos.get("explanation", ""),
            )

        except Exception as e:
            logger.error(f"Error generando cambio para {file_path}: {e}")
            return None

    def _generate_new_file(
        self,
        task: str,
        step_description: str,
        file_path: str,
        repo_context: str,
    ) -> CodeChange | None:
        """
        Genera contenido para un archivo nuevo.

        Args:
            task: Descripción de la tarea.
            step_description: Descripción del paso.
            file_path: Ruta del nuevo archivo.
            repo_context: Contexto del repositorio.

        Returns:
            CodeChange con el nuevo archivo, o None si falla.
        """
        prompt = self.CREATE_FILE_PROMPT.format(
            task=task,
            step_description=step_description,
            file_path=file_path,
            repo_context=repo_context,
        )

        try:
            respuesta = self._client.generate(
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=4096,
                system_override=self.AGENT_SYSTEM,
            )

            datos = self._parse_json_response(respuesta.content)
            if not datos:
                return None

            return CodeChange(
                file=file_path,
                action="create",
                modified=datos.get("file_content", ""),
                explanation=datos.get("explanation", ""),
            )

        except Exception as e:
            logger.error(f"Error generando nuevo archivo {file_path}: {e}")
            return None

    def _validate_changes(self, changes: list[CodeChange]) -> SafetyResult:
        """
        Valida todos los cambios contra las reglas de seguridad.

        Verifica:
        1. Cada archivo está permitido
        2. El contenido no tiene patrones peligrosos
        3. El tamaño total está dentro de los límites

        Args:
            changes: Lista de cambios a validar.

        Returns:
            SafetyResult general.
        """
        total_lines = sum(c.lines_changed for c in changes)

        # Verificar tamaño total
        size_check = self._safety.check_change_size(len(changes), total_lines)
        if not size_check.allowed:
            return size_check

        # Verificar contenido de cada cambio
        for change in changes:
            content_check = self._safety.check_content_safety(change.modified)
            if not content_check.allowed:
                return content_check

        from mikalia.agent.safety import SafetyResult as SR
        return SR(
            allowed=True,
            reason="Todos los cambios validados",
            severity=Severity.OK,
        )

    def _create_pr(
        self,
        repo: str,
        plan: TaskPlan,
        changes: list[CodeChange],
        task: str,
    ) -> PullRequest | None:
        """
        Crea branch, aplica cambios, y crea PR.

        Args:
            repo: Identificador del repo.
            plan: Plan de la tarea.
            changes: Cambios a aplicar.
            task: Descripción original de la tarea.

        Returns:
            PullRequest creado, o None si falla.
        """
        repo_path = self._repo_analyzer._resolve_repo_path(repo)

        pr_manager = PRManager(
            repo_path=str(repo_path),
            github_org=self._config.github.org,
            github_repo=self._config.github.blog_repo,
            safety_guard=self._safety,
        )

        # 1. Crear branch
        if not pr_manager.create_branch(plan.branch_name):
            logger.error("No se pudo crear el branch")
            return None

        # 2. Aplicar cambios a los archivos
        files_changed = []
        for change in changes:
            full_path = repo_path / change.file

            if change.action == "delete":
                if full_path.exists():
                    full_path.unlink()
                    files_changed.append(change.file)
            else:
                # create o modify
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(change.modified, encoding="utf-8")
                files_changed.append(change.file)

        # 3. Commit
        commit_msg = f"{self._config.git.commit_prefix} {plan.task_type.value}: {task}"
        try:
            pr_manager.commit_changes(files_changed, commit_msg)
        except Exception as e:
            logger.error(f"Error en commit: {e}")
            pr_manager.cleanup_branch(plan.branch_name)
            return None

        # 4. Push
        if not pr_manager.push_branch(plan.branch_name):
            logger.error("No se pudo pushear el branch")
            return None

        # 5. Crear PR
        changes_summary = [
            {"file": c.file, "action": c.action, "description": c.explanation}
            for c in changes
        ]
        pr_body = pr_manager.generate_pr_body(task, changes_summary)

        # Labels según tipo de tarea
        labels_config = self._config.github.pr_labels
        labels = labels_config.get(plan.task_type.value, ["mikalia-authored"])

        pr = pr_manager.create_pr(
            branch=plan.branch_name,
            title=f"{plan.task_type.value}: {task}",
            body=pr_body,
            labels=labels,
        )

        return pr

    def _generate_summary(self, task: str, changes: list[CodeChange]) -> str:
        """Genera resumen de los cambios realizados."""
        lineas = [f"Tarea: {task}", f"Archivos modificados: {len(changes)}", ""]
        for change in changes:
            icon = {"modify": "M", "create": "+", "delete": "-"}.get(change.action, "?")
            lineas.append(f"  [{icon}] {change.file}")
            if change.explanation:
                lineas.append(f"      {change.explanation[:100]}")
        return "\n".join(lineas)

    def _parse_json_response(self, response: str) -> dict | None:
        """Parsea respuesta JSON de Claude, manejando code fences y texto extra."""
        import re

        texto = response.strip()

        # Intentar extraer JSON de code fences (```json ... ```)
        fence_match = re.search(r"```(?:json)?\s*\n(.*?)```", texto, re.DOTALL)
        if fence_match:
            texto = fence_match.group(1).strip()

        # Intentar parseo directo
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            pass

        # Buscar primer { y último } para extraer JSON embebido
        first_brace = texto.find("{")
        last_brace = texto.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(texto[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("No se pudo parsear JSON de la respuesta")
        logger.warning(f"Respuesta raw (primeros 300 chars): {response[:300]}")
        return None

    def _safe_read(self, path: Path) -> str:
        """Lee un archivo de forma segura."""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
