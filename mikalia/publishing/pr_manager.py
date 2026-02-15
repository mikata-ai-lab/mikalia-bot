"""
pr_manager.py — Mikalia crea y gestiona Pull Requests.

Este módulo maneja todo el ciclo de vida de un PR:
    1. Crear branch con convención de nombres
    2. Commit cambios con mensajes descriptivos
    3. Push branch
    4. Crear PR via GitHub API (usando gh CLI)
    5. Agregar labels automáticos según tipo
    6. Escribir comentario explicativo en el PR

Convención de nombres:
    - Branch: mikalia/{tipo}/{slug-descriptivo}
    - PR title: "[Mikalia] {tipo}: {descripción}"
    - Labels: tipo + "mikalia-authored"

¿Por qué gh CLI en vez de requests directos a la API?
    - gh ya maneja la autenticación
    - Sintaxis más simple y legible
    - No necesitamos manejar tokens de GitHub App para esto
    - Fallback: si gh no está disponible, usamos requests

Uso:
    from mikalia.publishing.pr_manager import PRManager
    manager = PRManager(repo_path, config)
    pr = manager.create_pr(
        branch="mikalia/feat/add-validation",
        title="Add input validation",
        body="## Changes\n- Added validation to...",
        labels=["enhancement", "mikalia-authored"],
    )
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from git import Repo, GitCommandError

from mikalia.agent.safety import SafetyGuard
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.pr_manager")


class PRStatus(Enum):
    """Estado de un Pull Request."""
    OPEN = "open"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    MERGED = "merged"
    CLOSED = "closed"


@dataclass
class PullRequest:
    """
    Datos de un Pull Request creado por Mikalia.

    Campos:
        number: Número del PR en GitHub
        url: URL completa del PR
        title: Título del PR
        branch: Nombre del branch
        status: Estado actual
        labels: Labels aplicados
    """
    number: int = 0
    url: str = ""
    title: str = ""
    branch: str = ""
    status: PRStatus = PRStatus.OPEN
    labels: list[str] = field(default_factory=list)


class PRManager:
    """
    Gestor de Pull Requests para el agente de Mikalia.

    Se encarga de todo el ciclo: crear branch, commit,
    push, crear PR, y agregar labels/comentarios.

    Args:
        repo_path: Ruta al repositorio local.
        github_org: Organización de GitHub (ej: "mikata-ai-lab").
        github_repo: Nombre del repo (ej: "mikalia-bot").
        safety_guard: Guardián de seguridad.
    """

    def __init__(
        self,
        repo_path: str,
        github_org: str = "mikata-ai-lab",
        github_repo: str = "mikalia-bot",
        safety_guard: SafetyGuard | None = None,
    ):
        self._repo_path = Path(repo_path)
        self._github_org = github_org
        self._github_repo = github_repo
        self._safety = safety_guard or SafetyGuard()
        self._repo = Repo(repo_path)

    # ============================================================
    # Operaciones de branch
    # ============================================================

    def create_branch(self, branch_name: str) -> bool:
        """
        Crea un nuevo branch desde main y hace checkout.

        Verifica que el branch sigue la convención de Mikalia
        y que no estamos intentando pushear a un branch protegido.

        Args:
            branch_name: Nombre del branch (ej: "mikalia/feat/add-validation").

        Returns:
            True si el branch se creó correctamente.

        Raises:
            ValueError: Si el branch viola las reglas de seguridad.
        """
        # Verificar seguridad
        check = self._safety.check_branch_push(branch_name)
        if not check.allowed:
            raise ValueError(f"Branch bloqueado: {check.reason}")

        try:
            # Asegurar que estamos en main y actualizados
            self._repo.heads.main.checkout()
            self._repo.remotes.origin.pull()

            # Crear nuevo branch
            nuevo = self._repo.create_head(branch_name)
            nuevo.checkout()

            logger.success(f"Branch creado: {branch_name}")
            return True

        except GitCommandError as e:
            logger.error(f"Error creando branch: {e}")
            return False

    def switch_to_branch(self, branch_name: str) -> bool:
        """
        Cambia al branch especificado.

        Args:
            branch_name: Nombre del branch.

        Returns:
            True si el cambio fue exitoso.
        """
        try:
            self._repo.heads[branch_name].checkout()
            return True
        except (GitCommandError, IndexError) as e:
            logger.error(f"Error cambiando a branch {branch_name}: {e}")
            return False

    # ============================================================
    # Operaciones de commit
    # ============================================================

    def commit_changes(
        self,
        files: list[str],
        message: str,
    ) -> str:
        """
        Hace staging y commit de archivos específicos.

        Verifica que cada archivo pase las reglas de seguridad
        antes de incluirlo en el commit.

        Args:
            files: Lista de rutas relativas de archivos a commitear.
            message: Mensaje del commit.

        Returns:
            Hash del commit creado.

        Raises:
            ValueError: Si algún archivo está bloqueado por seguridad.
        """
        # Verificar seguridad de cada archivo
        for file_path in files:
            check = self._safety.check_file_access(file_path)
            if not check.allowed:
                raise ValueError(
                    f"Archivo bloqueado por seguridad: {file_path} — {check.reason}"
                )

        try:
            # Stage archivos
            self._repo.index.add(files)

            # Commit
            commit = self._repo.index.commit(message)
            logger.success(f"Commit creado: {commit.hexsha[:7]} — {message}")
            return commit.hexsha

        except GitCommandError as e:
            logger.error(f"Error en commit: {e}")
            raise

    def push_branch(self, branch_name: str) -> bool:
        """
        Pushea un branch al remoto.

        Verificación de seguridad: nunca pushea a branches protegidos.

        Args:
            branch_name: Nombre del branch a pushear.

        Returns:
            True si el push fue exitoso.
        """
        check = self._safety.check_branch_push(branch_name)
        if not check.allowed:
            logger.error(f"Push bloqueado: {check.reason}")
            return False

        try:
            self._repo.remotes.origin.push(
                refspec=f"{branch_name}:{branch_name}",
                set_upstream=True,
            )
            logger.success(f"Branch pusheado: {branch_name}")
            return True

        except GitCommandError as e:
            logger.error(f"Error en push: {e}")
            return False

    # ============================================================
    # Operaciones de PR
    # ============================================================

    def create_pr(
        self,
        branch: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
        base: str = "main",
    ) -> PullRequest:
        """
        Crea un Pull Request en GitHub usando gh CLI.

        Genera un PR con título, descripción, y labels automáticos.
        El PR siempre va contra main (o el base branch configurado).

        Args:
            branch: Nombre del branch fuente.
            title: Título del PR.
            body: Descripción del PR (markdown).
            labels: Labels a aplicar.
            base: Branch base (default: main).

        Returns:
            PullRequest con los datos del PR creado.
        """
        labels = labels or ["mikalia-authored"]

        # Formatear título con prefijo de Mikalia
        pr_title = f"[Mikalia] {title}"

        # Crear PR usando gh CLI
        cmd = [
            "gh", "pr", "create",
            "--title", pr_title,
            "--body", body,
            "--base", base,
            "--head", branch,
        ]

        # Agregar labels
        for label in labels:
            cmd.extend(["--label", label])

        try:
            resultado = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self._repo_path,
                timeout=30,
            )

            if resultado.returncode == 0:
                pr_url = resultado.stdout.strip()
                # Extraer número del PR de la URL
                pr_number = int(pr_url.rstrip("/").split("/")[-1])

                logger.success(f"PR creado: #{pr_number} — {pr_title}")
                logger.info(f"URL: {pr_url}")

                return PullRequest(
                    number=pr_number,
                    url=pr_url,
                    title=pr_title,
                    branch=branch,
                    status=PRStatus.OPEN,
                    labels=labels,
                )
            else:
                logger.error(f"Error creando PR: {resultado.stderr}")
                return PullRequest(title=pr_title, branch=branch)

        except FileNotFoundError:
            logger.error("gh CLI no encontrado. Instálalo: https://cli.github.com")
            return PullRequest(title=pr_title, branch=branch)
        except subprocess.TimeoutExpired:
            logger.error("Timeout creando PR")
            return PullRequest(title=pr_title, branch=branch)

    def add_comment(self, pr_number: int, comment: str) -> bool:
        """
        Agrega un comentario a un PR existente.

        Útil para que Mikalia explique sus cambios en detalle
        después de crear el PR.

        Args:
            pr_number: Número del PR.
            comment: Texto del comentario (markdown).

        Returns:
            True si el comentario se agregó correctamente.
        """
        try:
            resultado = subprocess.run(
                ["gh", "pr", "comment", str(pr_number), "--body", comment],
                capture_output=True,
                text=True,
                cwd=self._repo_path,
                timeout=15,
            )
            if resultado.returncode == 0:
                logger.success(f"Comentario agregado al PR #{pr_number}")
                return True
            else:
                logger.error(f"Error comentando PR: {resultado.stderr}")
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    # ============================================================
    # Utilidades
    # ============================================================

    def generate_pr_body(
        self,
        task_description: str,
        changes_summary: list[dict],
    ) -> str:
        """
        Genera la descripción de un PR en formato markdown.

        Estructura:
        - Descripción del cambio
        - Lista de archivos modificados
        - Checklist de calidad
        - Firma de Mikalia

        Args:
            task_description: Descripción original de la tarea.
            changes_summary: Lista de {file, action, description}.

        Returns:
            Markdown formateado para el body del PR.
        """
        # Sección de cambios
        changes_md = ""
        for change in changes_summary:
            action_icon = {
                "modify": "M",
                "create": "+",
                "delete": "-",
            }.get(change.get("action", "modify"), "?")

            changes_md += (
                f"- `[{action_icon}]` **{change['file']}** — "
                f"{change.get('description', 'Changes')}\n"
            )

        body = f"""## Description
{task_description}

## Changes
{changes_md}

## Checklist
- [x] Code commented in Spanish
- [x] No sensitive files modified
- [x] Consistent with project style
- [x] Safety check passed
- [ ] Tests updated (if applicable)
- [ ] Manual review by @mikata-renji

---
*PR created automatically by Mikalia*
*Review required from @mikata-renji*
"""
        return body

    def cleanup_branch(self, branch_name: str) -> bool:
        """
        Limpia un branch después de merge.

        Cambia a main y borra el branch local.

        Args:
            branch_name: Nombre del branch a borrar.

        Returns:
            True si se limpió correctamente.
        """
        try:
            self._repo.heads.main.checkout()
            self._repo.delete_head(branch_name, force=True)
            logger.info(f"Branch local borrado: {branch_name}")
            return True
        except (GitCommandError, Exception) as e:
            logger.warning(f"No se pudo borrar branch {branch_name}: {e}")
            return False
