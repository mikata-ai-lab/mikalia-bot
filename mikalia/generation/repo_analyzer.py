"""
repo_analyzer.py — Mikalia lee y entiende repositorios.

Este módulo permite a Mikalia clonar/leer un repo de GitHub
y extraer información relevante para generar posts técnicos
informados y precisos.

Flujo:
    1. Clonar repo (o pull si ya existe en cache local)
    2. Leer README.md para entender el propósito
    3. Analizar estructura de archivos (tree)
    4. Identificar archivos clave (entry points, configs)
    5. Leer archivos clave y extraer patrones
    6. Generar un "contexto" que se pasa al post_generator

¿Por qué no pasar TODO el código a Claude?
    - Los repos pueden ser enormes (exceden context window)
    - Es más eficiente extraer lo relevante primero
    - Mikalia aprende a priorizar (como un dev real)

Seguridad:
    - Solo clona repos que Mikata ha configurado o repos públicos
    - Cache local para no clonar cada vez
    - Limpieza automática de repos viejos

Uso:
    from mikalia.generation.repo_analyzer import RepoAnalyzer
    analyzer = RepoAnalyzer(config)
    context = analyzer.analyze("mikata-ai-lab/mikalia-bot")
    # Luego pasas context.to_prompt() al post_generator
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from git import Repo, GitCommandError

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.repo_analyzer")

# Extensiones de código que Mikalia sabe leer
# Organizadas por lenguaje para estadísticas
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "Python": [".py"],
    "JavaScript": [".js", ".jsx", ".mjs"],
    "TypeScript": [".ts", ".tsx"],
    "Rust": [".rs"],
    "Go": [".go"],
    "Java": [".java"],
    "C#": [".cs"],
    "C/C++": [".c", ".cpp", ".h", ".hpp"],
    "Ruby": [".rb"],
    "PHP": [".php"],
    "Shell": [".sh", ".bash"],
    "Markdown": [".md"],
    "YAML": [".yml", ".yaml"],
    "JSON": [".json"],
    "TOML": [".toml"],
    "HTML": [".html"],
    "CSS": [".css", ".scss", ".sass"],
}

# Archivos que suelen ser importantes en un repo
# Mikalia los busca primero para entender el proyecto
KEY_FILE_PATTERNS = [
    "README.md",
    "README.rst",
    "setup.py",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".github/workflows/*.yml",
    "config.*",
    "main.*",
    "app.*",
    "index.*",
]

# Directorios que siempre ignoramos (no aportan contexto útil)
IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "egg-info", ".eggs", "target", "vendor",
    ".next", ".nuxt", "coverage", ".coverage",
}

# Extensiones binarias que no podemos leer
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".whl",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".pyc", ".pyo", ".class", ".o",
    ".lock", ".min.js", ".min.css",
}


@dataclass
class RepoContext:
    """
    Contexto extraído de un repositorio.

    Contiene toda la información que Mikalia necesita para
    escribir un post informado sobre el repo o sus tecnologías.

    Campos:
        repo_name: Nombre del repo (ej: "mikata-ai-lab/mikalia-bot")
        description: Descripción extraída del README
        structure: Árbol de archivos (formato texto)
        readme_content: Contenido del README (truncado si es muy largo)
        key_files: Diccionario {ruta: contenido} de archivos clave
        language_stats: Estadísticas de lenguajes detectados
        total_files: Número total de archivos
    """
    repo_name: str
    description: str = ""
    structure: str = ""
    readme_content: str = ""
    key_files: dict[str, str] = field(default_factory=dict)
    language_stats: dict[str, int] = field(default_factory=dict)
    total_files: int = 0

    def to_prompt(self, max_tokens: int = 8000) -> str:
        """
        Convierte el contexto del repo a texto para incluir en el prompt.

        Formato diseñado para darle a Claude la información más útil
        primero (README, estructura) y luego el código clave.

        Args:
            max_tokens: Límite aproximado de caracteres (~4 chars/token)

        Returns:
            String formateado para incluir en el prompt de generación.
        """
        # Construir el contexto priorizando información
        partes = []

        partes.append(f"=== Repository: {self.repo_name} ===")

        if self.description:
            partes.append(f"\nDescription: {self.description}")

        if self.language_stats:
            stats = ", ".join(
                f"{lang}: {count} files"
                for lang, count in sorted(
                    self.language_stats.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:5]  # Top 5 lenguajes
            )
            partes.append(f"\nLanguages: {stats}")
            partes.append(f"Total files: {self.total_files}")

        if self.structure:
            partes.append(f"\n--- File Structure ---\n{self.structure}")

        if self.readme_content:
            # Truncar README si es muy largo
            readme = self.readme_content[:3000]
            if len(self.readme_content) > 3000:
                readme += "\n... (truncated)"
            partes.append(f"\n--- README ---\n{readme}")

        # Agregar archivos clave si hay espacio
        texto_actual = "\n".join(partes)
        max_chars = max_tokens * 4  # Aproximación chars → tokens

        if self.key_files and len(texto_actual) < max_chars:
            partes.append("\n--- Key Files ---")
            for ruta, contenido in self.key_files.items():
                fragmento = f"\n## {ruta}\n```\n{contenido}\n```"
                if len(texto_actual) + len(fragmento) > max_chars:
                    partes.append("\n... (more files omitted for brevity)")
                    break
                partes.append(fragmento)
                texto_actual += fragmento

        return "\n".join(partes)


class RepoAnalyzer:
    """
    Analiza repositorios de GitHub para extraer contexto.

    Puede trabajar con repos locales o clonar repos remotos
    a un directorio de cache.

    Args:
        cache_dir: Directorio para cachear repos clonados.
                   Default: ~/.mikalia/repos
    """

    def __init__(self, cache_dir: str | None = None):
        # Directorio donde se guardan los repos clonados
        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            self._cache_dir = Path.home() / ".mikalia" / "repos"

        # Crear directorio de cache si no existe
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def analyze(
        self,
        repo: str,
        focus_topic: str | None = None,
        max_file_size: int = 50_000,
    ) -> RepoContext:
        """
        Analiza un repositorio y extrae contexto relevante.

        Acepta repos en varios formatos:
        - Ruta local: "/path/to/repo" o "C:\\path\\to\\repo"
        - GitHub short: "owner/repo"
        - GitHub URL: "https://github.com/owner/repo"

        Args:
            repo: Identificador del repo (local, GitHub short, o URL)
            focus_topic: Tema específico para enfocar el análisis
            max_file_size: Tamaño máximo de archivo a leer (bytes)

        Returns:
            RepoContext con toda la información extraída.
        """
        logger.info(f"Analizando repositorio: {repo}")

        # Resolver la ruta local del repo
        repo_path = self._resolve_repo_path(repo)
        repo_name = self._extract_repo_name(repo)

        logger.step(1, 5, "Leyendo README...")
        readme = self._read_readme(repo_path)

        logger.step(2, 5, "Analizando estructura...")
        estructura, total_files = self._analyze_structure(repo_path)

        logger.step(3, 5, "Detectando lenguajes...")
        lang_stats = self._detect_languages(repo_path)

        logger.step(4, 5, "Identificando archivos clave...")
        key_files = self._identify_and_read_key_files(
            repo_path, focus_topic, max_file_size
        )

        logger.step(5, 5, "Generando contexto...")

        # Extraer descripción del README (primera línea no-título)
        description = self._extract_description(readme)

        contexto = RepoContext(
            repo_name=repo_name,
            description=description,
            structure=estructura,
            readme_content=readme,
            key_files=key_files,
            language_stats=lang_stats,
            total_files=total_files,
        )

        logger.success(
            f"Repo analizado: {total_files} archivos, "
            f"{len(key_files)} archivos clave, "
            f"{len(lang_stats)} lenguajes detectados"
        )

        return contexto

    def analyze_local(self, path: str, focus_topic: str | None = None) -> RepoContext:
        """
        Atajo para analizar un repo local directamente.

        Útil cuando ya tienes el repo en tu máquina y no
        necesitas clonar nada.

        Args:
            path: Ruta al directorio del repo local.
            focus_topic: Tema para enfocar el análisis.

        Returns:
            RepoContext con la información extraída.
        """
        return self.analyze(path, focus_topic)

    def _resolve_repo_path(self, repo: str) -> Path:
        """
        Resuelve el identificador del repo a una ruta local.

        Si es un repo remoto, lo clona o actualiza en el cache.
        Si es una ruta local, la usa directamente.

        Args:
            repo: Identificador del repo.

        Returns:
            Path al directorio del repo.

        Raises:
            FileNotFoundError: Si el repo local no existe.
            GitCommandError: Si no se puede clonar el repo remoto.
        """
        # Caso 1: Ruta local (absoluta o con separadores de ruta)
        local_path = Path(repo)
        if local_path.is_absolute() or os.sep in repo:
            if not local_path.exists():
                raise FileNotFoundError(f"Repo local no encontrado: {repo}")
            return local_path

        # Caso 2: URL de GitHub completa
        if repo.startswith("https://github.com/"):
            # Extraer owner/repo de la URL
            repo = repo.replace("https://github.com/", "").rstrip("/").rstrip(".git")

        # Caso 3: Formato "owner/repo" → clonar o actualizar
        if "/" in repo:
            return self._clone_or_pull(repo)

        raise ValueError(
            f"Formato de repo no reconocido: {repo}. "
            "Usa: ruta local, 'owner/repo', o URL de GitHub"
        )

    def _clone_or_pull(self, repo_slug: str) -> Path:
        """
        Clona el repo si no está en cache, o hace pull si ya existe.

        El cache evita clonar el mismo repo cada vez que se genera
        un post. Después de N días se limpia automáticamente.

        Args:
            repo_slug: Repo en formato "owner/repo".

        Returns:
            Path al directorio del repo clonado.
        """
        # Directorio de cache: ~/.mikalia/repos/owner/repo
        cache_path = self._cache_dir / repo_slug.replace("/", os.sep)

        if cache_path.exists() and (cache_path / ".git").exists():
            # Repo ya clonado → hacer pull para actualizar
            logger.info(f"Repo en cache, actualizando: {repo_slug}")
            try:
                git_repo = Repo(cache_path)
                git_repo.remotes.origin.pull()
                return cache_path
            except GitCommandError as e:
                # Si pull falla, re-clonar
                logger.warning(f"Pull falló, re-clonando: {e}")
                shutil.rmtree(cache_path, ignore_errors=True)

        # Clonar repo
        url = f"https://github.com/{repo_slug}.git"
        logger.info(f"Clonando repo: {url}")

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            Repo.clone_from(url, cache_path, depth=1)  # Shallow clone
            return cache_path
        except GitCommandError as e:
            raise GitCommandError(
                f"No se pudo clonar {repo_slug}: {e}"
            ) from e

    def _extract_repo_name(self, repo: str) -> str:
        """Extrae un nombre legible del identificador del repo."""
        if repo.startswith("https://github.com/"):
            return repo.replace("https://github.com/", "").rstrip("/").rstrip(".git")

        local_path = Path(repo)
        if local_path.is_absolute() or os.sep in repo:
            return local_path.name

        return repo

    def _read_readme(self, repo_path: Path) -> str:
        """
        Lee el README del repo.

        Busca varios nombres posibles (README.md, readme.md,
        README.rst, etc.) y retorna el contenido del primero
        que encuentre.

        Args:
            repo_path: Ruta al directorio del repo.

        Returns:
            Contenido del README, o string vacío si no hay.
        """
        nombres_posibles = [
            "README.md", "readme.md", "Readme.md",
            "README.rst", "readme.rst",
            "README.txt", "readme.txt",
            "README", "readme",
        ]

        for nombre in nombres_posibles:
            ruta = repo_path / nombre
            if ruta.exists():
                try:
                    return ruta.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

        return ""

    def _analyze_structure(
        self,
        repo_path: Path,
        max_depth: int = 3,
    ) -> tuple[str, int]:
        """
        Genera un árbol de archivos del repo (similar a `tree`).

        Solo muestra hasta cierta profundidad para no abrumar.
        Ignora directorios de build, cache, etc.

        Args:
            repo_path: Ruta al directorio del repo.
            max_depth: Profundidad máxima del árbol.

        Returns:
            Tupla de (árbol como string, total de archivos).
        """
        lineas = []
        total_archivos = 0

        def _recorrer(directorio: Path, prefijo: str, profundidad: int):
            nonlocal total_archivos

            if profundidad > max_depth:
                return

            try:
                # Obtener y ordenar entradas (directorios primero)
                entradas = sorted(
                    directorio.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except PermissionError:
                return

            # Filtrar entradas ignoradas
            entradas = [
                e for e in entradas
                if e.name not in IGNORE_DIRS
                and not e.name.startswith(".")
            ]

            for i, entrada in enumerate(entradas):
                es_ultimo = i == len(entradas) - 1
                conector = "└── " if es_ultimo else "├── "
                extension = "    " if es_ultimo else "│   "

                if entrada.is_dir():
                    # Contar archivos dentro sin mostrar todo
                    contenido_dir = list(entrada.rglob("*"))
                    n_archivos = sum(1 for f in contenido_dir if f.is_file())
                    total_archivos += n_archivos

                    lineas.append(f"{prefijo}{conector}{entrada.name}/")
                    _recorrer(entrada, prefijo + extension, profundidad + 1)
                else:
                    total_archivos += 1
                    lineas.append(f"{prefijo}{conector}{entrada.name}")

        lineas.append(repo_path.name + "/")
        _recorrer(repo_path, "", 1)

        return "\n".join(lineas[:100]), total_archivos  # Max 100 líneas

    def _detect_languages(self, repo_path: Path) -> dict[str, int]:
        """
        Detecta lenguajes de programación en el repo.

        Cuenta archivos por extensión y mapea a lenguajes conocidos.
        Útil para entender la tecnología del proyecto.

        Args:
            repo_path: Ruta al directorio del repo.

        Returns:
            Diccionario {lenguaje: cantidad de archivos}.
        """
        stats: dict[str, int] = {}

        # Invertir el mapa: extensión → lenguaje
        ext_to_lang = {}
        for lang, exts in LANGUAGE_EXTENSIONS.items():
            for ext in exts:
                ext_to_lang[ext] = lang

        try:
            for archivo in repo_path.rglob("*"):
                if not archivo.is_file():
                    continue

                # Ignorar directorios especiales
                partes = archivo.relative_to(repo_path).parts
                if any(parte in IGNORE_DIRS or parte.startswith(".") for parte in partes):
                    continue

                ext = archivo.suffix.lower()
                if ext in ext_to_lang:
                    lang = ext_to_lang[ext]
                    stats[lang] = stats.get(lang, 0) + 1
        except Exception:
            pass

        return stats

    def _identify_and_read_key_files(
        self,
        repo_path: Path,
        focus_topic: str | None,
        max_file_size: int,
    ) -> dict[str, str]:
        """
        Identifica y lee archivos clave del repo.

        Prioriza:
        1. Archivos de configuración (setup.py, package.json, etc.)
        2. Entry points (main.py, app.py, index.ts, etc.)
        3. Archivos relacionados con el tema (si se especificó)

        Args:
            repo_path: Ruta al directorio del repo.
            focus_topic: Tema para buscar archivos relacionados.
            max_file_size: Tamaño máximo de archivo a leer.

        Returns:
            Diccionario {ruta_relativa: contenido}.
        """
        archivos_clave: dict[str, str] = {}

        # Buscar archivos por patrones conocidos
        for patron in KEY_FILE_PATTERNS:
            for ruta in repo_path.glob(patron):
                if ruta.is_file() and ruta.stat().st_size <= max_file_size:
                    rel = str(ruta.relative_to(repo_path))
                    contenido = self._safe_read(ruta)
                    if contenido:
                        archivos_clave[rel] = contenido

        # Si hay un tema de enfoque, buscar archivos relacionados
        if focus_topic:
            topic_keywords = focus_topic.lower().split()
            for archivo in repo_path.rglob("*"):
                if not archivo.is_file():
                    continue
                if archivo.stat().st_size > max_file_size:
                    continue

                # Ignorar directorios especiales y binarios
                partes = archivo.relative_to(repo_path).parts
                if any(p in IGNORE_DIRS or p.startswith(".") for p in partes):
                    continue
                if archivo.suffix.lower() in BINARY_EXTENSIONS:
                    continue

                # Buscar keywords en el nombre del archivo
                nombre_lower = archivo.name.lower()
                if any(kw in nombre_lower for kw in topic_keywords):
                    rel = str(archivo.relative_to(repo_path))
                    if rel not in archivos_clave:
                        contenido = self._safe_read(archivo)
                        if contenido:
                            archivos_clave[rel] = contenido

                # Limitar a 15 archivos para no exceder el contexto
                if len(archivos_clave) >= 15:
                    break

        return archivos_clave

    def _safe_read(self, path: Path, max_lines: int = 200) -> str:
        """
        Lee un archivo de texto de forma segura.

        Maneja errores de encoding y trunca archivos muy largos.

        Args:
            path: Ruta al archivo.
            max_lines: Máximo de líneas a leer.

        Returns:
            Contenido del archivo, o string vacío si falla.
        """
        try:
            # Ignorar binarios por extensión
            if path.suffix.lower() in BINARY_EXTENSIONS:
                return ""

            texto = path.read_text(encoding="utf-8", errors="replace")
            lineas = texto.splitlines()

            if len(lineas) > max_lines:
                return "\n".join(lineas[:max_lines]) + f"\n... ({len(lineas)} lines total)"

            return texto
        except Exception:
            return ""

    def _extract_description(self, readme: str) -> str:
        """
        Extrae una descripción corta del README.

        Busca la primera línea de texto que no sea un heading,
        badge, o línea vacía. Esa suele ser la descripción del proyecto.

        Args:
            readme: Contenido del README.

        Returns:
            Descripción del proyecto (max 200 chars).
        """
        if not readme:
            return ""

        for linea in readme.splitlines():
            linea = linea.strip()
            # Ignorar líneas vacías, headings, badges, separadores
            if not linea:
                continue
            if linea.startswith("#"):
                continue
            if linea.startswith("![") or linea.startswith("[!["):
                continue
            if linea.startswith("---") or linea.startswith("==="):
                continue
            if linea.startswith(">"):
                # Blockquotes a veces tienen la descripción
                return linea.lstrip("> ")[:200]

            return linea[:200]

        return ""

    def cleanup_cache(self, max_age_days: int = 7) -> int:
        """
        Limpia repos viejos del cache.

        Borra repos que no se han usado en N días para
        liberar espacio en disco.

        Args:
            max_age_days: Edad máxima en días antes de borrar.

        Returns:
            Número de repos eliminados.
        """
        import time

        eliminados = 0
        ahora = time.time()
        max_age_secs = max_age_days * 86400

        if not self._cache_dir.exists():
            return 0

        for owner_dir in self._cache_dir.iterdir():
            if not owner_dir.is_dir():
                continue
            for repo_dir in owner_dir.iterdir():
                if not repo_dir.is_dir():
                    continue
                # Usar la fecha de modificación más reciente
                try:
                    ultima_mod = max(
                        f.stat().st_mtime
                        for f in repo_dir.rglob("*")
                        if f.is_file()
                    )
                    if ahora - ultima_mod > max_age_secs:
                        shutil.rmtree(repo_dir, ignore_errors=True)
                        eliminados += 1
                        logger.info(f"Cache limpiado: {owner_dir.name}/{repo_dir.name}")
                except (ValueError, OSError):
                    continue

        return eliminados
