"""
git_ops.py — Mikalia habla con Git.

Este archivo maneja todas las operaciones Git necesarias para
publicar contenido en el blog. Usa GitPython para interactuar
con el repositorio de forma programática.

Flujo para F1 (push directo a main):
    1. Clonar o abrir el repo del blog
    2. git pull origin main (sincronizar)
    3. Escribir archivos generados en content/blog/
    4. git add (los archivos nuevos)
    5. git commit -m "✨ New post: {title} — by Mikalia"
    6. git push origin main
    7. GitHub Actions deploya automáticamente

Flujo para F3 (PRs — futuro):
    1. git checkout -b mikalia/{tipo}/{slug}
    2. Hacer cambios
    3. git commit + git push
    4. Crear PR via GitHub API

¿Por qué GitPython y no subprocess?
    - API más limpia y Pythonica
    - Manejo de errores más granular
    - No hay que parsear output de texto
    - Type hints y autocompletado

Uso:
    from mikalia.publishing.git_ops import GitOperations
    git = GitOperations(repo_path, config)
    git.sync_repo()
    git.publish_post(files, "My Post Title")
"""

from __future__ import annotations

from pathlib import Path

import git as gitpython

from mikalia.config import AppConfig
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.git")


class GitOperations:
    """
    Gestiona operaciones Git para publicar contenido.

    Abstrae todas las interacciones con Git para que el resto
    del código solo necesite llamar publish_post() sin preocuparse
    por los detalles de Git.

    Args:
        repo_path: Ruta al repositorio local del blog
        config: Configuración de la app
    """

    def __init__(self, repo_path: str | Path, config: AppConfig):
        self._repo_path = Path(repo_path)
        self._config = config
        self._repo: gitpython.Repo | None = None

    def _get_repo(self) -> gitpython.Repo:
        """
        Obtiene o abre el repositorio Git.

        Si el repo ya fue abierto, lo reutiliza (eficiente).
        Si no, lo abre desde la ruta configurada.

        Returns:
            Instancia de git.Repo lista para operar.

        Raises:
            git.InvalidGitRepositoryError: Si la ruta no es un repo Git.
            FileNotFoundError: Si la ruta no existe.
        """
        if self._repo is None:
            if not self._repo_path.exists():
                raise FileNotFoundError(
                    f"No se encontró el repositorio en: {self._repo_path}\n"
                    "Verifica que BLOG_REPO_PATH en .env sea correcto."
                )
            self._repo = gitpython.Repo(self._repo_path)
        return self._repo

    def sync_repo(self) -> bool:
        """
        Sincroniza el repo local con el remoto (git pull).

        Es importante hacer pull antes de push para evitar
        conflictos. Si hay cambios locales sin commit, se
        detiene y avisa.

        Returns:
            True si la sincronización fue exitosa.

        Raises:
            RuntimeError: Si hay cambios locales sin commit.
        """
        repo = self._get_repo()

        # Verificar estado limpio
        if repo.is_dirty(untracked_files=True):
            logger.warning("El repo tiene cambios sin commit")
            # No fallamos, solo advertimos — los cambios nuevos se agregarán

        # Pull cambios remotos
        branch = self._config.git.default_branch
        try:
            origin = repo.remotes.origin
            origin.pull(branch)
            logger.info(f"Repo sincronizado con origin/{branch}")
            return True
        except gitpython.GitCommandError as e:
            logger.error(f"Error al sincronizar: {e}")
            return False

    def publish_post(
        self,
        files: dict[Path, str],
        title: str,
    ) -> str:
        """
        Publica un post: escribe archivos, commit y push.

        Este es el método principal de F1. Toma los archivos
        formateados por HugoFormatter y los publica en el blog.

        Args:
            files: Dict de {ruta_relativa: contenido} a escribir
            title: Título del post (para el mensaje de commit)

        Returns:
            Hash del commit creado.

        Raises:
            RuntimeError: Si git push falla.
        """
        repo = self._get_repo()

        # Paso 1: Escribir archivos al disco
        archivos_escritos = []
        for ruta_relativa, contenido in files.items():
            ruta_completa = self._repo_path / ruta_relativa

            # Crear directorio si no existe
            ruta_completa.parent.mkdir(parents=True, exist_ok=True)

            # Escribir archivo
            ruta_completa.write_text(contenido, encoding="utf-8")
            archivos_escritos.append(str(ruta_relativa))
            logger.info(f"Archivo escrito: {ruta_relativa}")

        # Paso 2: git add
        repo.index.add(archivos_escritos)

        # Paso 3: git commit
        mensaje = self._generate_commit_message(title)
        commit = repo.index.commit(mensaje)
        logger.info(f"Commit creado: {commit.hexsha[:7]} — {mensaje}")

        # Paso 4: git push
        branch = self._config.git.default_branch
        try:
            origin = repo.remotes.origin
            origin.push(branch)
            logger.success(f"Push exitoso a origin/{branch}")
        except gitpython.GitCommandError as e:
            logger.error(f"Error en git push: {e}")
            raise RuntimeError(f"Git push falló: {e}") from e

        return commit.hexsha

    def write_files_only(self, files: dict[Path, str]) -> list[Path]:
        """
        Solo escribe archivos al disco SIN hacer commit ni push.

        Útil para los modos --dry-run y --preview donde queremos
        ver el resultado sin publicar.

        Args:
            files: Dict de {ruta_relativa: contenido} a escribir.

        Returns:
            Lista de rutas absolutas de los archivos escritos.
        """
        rutas_escritas = []
        for ruta_relativa, contenido in files.items():
            ruta_completa = self._repo_path / ruta_relativa

            # Crear directorio si no existe
            ruta_completa.parent.mkdir(parents=True, exist_ok=True)

            # Escribir archivo
            ruta_completa.write_text(contenido, encoding="utf-8")
            rutas_escritas.append(ruta_completa)
            logger.info(f"Archivo escrito (local): {ruta_relativa}")

        return rutas_escritas

    def _generate_commit_message(self, title: str) -> str:
        """
        Genera un mensaje de commit descriptivo.

        Formato: {emoji} New post: {título} — by Mikalia

        Ejemplo:
            ✨ New post: Building AI Agents with Python — by Mikalia

        Args:
            title: Título del post.

        Returns:
            Mensaje de commit formateado.
        """
        prefix = self._config.git.commit_prefix
        return f"{prefix} New post: {title} — by Mikalia"
