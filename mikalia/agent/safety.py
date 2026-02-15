"""
safety.py — Los guardrails de Mikalia.

Este es probablemente el archivo MÁS IMPORTANTE de todo el bot.
Define los límites de lo que Mikalia puede y no puede hacer.
Sin estos guardrails, un agente autónomo podría causar daño.

Principio de diseño: "Mikalia es poderosa pero prudente."
    - Como 2B: fuerte pero con propósito (力)
    - Como Aigis: analítica y calmada (静)

Reglas ABSOLUTAS (nunca se pueden desactivar):
    1. NUNCA modificar archivos de secrets/credentials
    2. NUNCA pushear directo a main (siempre PR en F3)
    3. NUNCA ejecutar código generado (solo proponerlo)
    4. NUNCA borrar branches protegidas
    5. NUNCA hacer force push
    6. NUNCA modificar GitHub Actions workflows sin aprobación explícita
    7. NUNCA acceder a repos no configurados

Reglas configurables:
    - max_files_per_pr: 10 (default)
    - max_lines_changed: 500 (default)
    - allowed_file_extensions: [".py", ".js", ".ts", ".md", ...]
    - blocked_paths: [".env", "secrets/", ".github/workflows/"]
    - require_tests: false (default)

Si una tarea excede los límites, Mikalia:
    1. Se detiene inmediatamente
    2. Notifica a Mikata-kun por Telegram
    3. Explica qué quería hacer y por qué se detuvo
    4. Pide instrucciones

Uso:
    from mikalia.agent.safety import SafetyGuard, Severity
    guard = SafetyGuard(config)
    result = guard.check_file_access("path/to/file.py")
    if not result.allowed:
        print(f"BLOCKED: {result.reason}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath

from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.safety")


class Severity(Enum):
    """
    Niveles de severidad para verificaciones de seguridad.

    OK       → Todo bien, puede proceder
    WARNING  → Puede proceder pero con precaución
    BLOCKED  → No puede proceder, necesita cambiar el enfoque
    CRITICAL → Violación de regla absoluta, detener inmediatamente
    """
    OK = "ok"
    WARNING = "warning"
    BLOCKED = "blocked"
    CRITICAL = "critical"


@dataclass
class SafetyResult:
    """
    Resultado de una verificación de seguridad.

    Campos:
        allowed: Si la acción está permitida
        reason: Explicación de por qué fue permitida o bloqueada
        severity: Nivel de severidad
        details: Información adicional para el log/notificación
    """
    allowed: bool
    reason: str
    severity: Severity
    details: str = ""


@dataclass
class SafetyConfig:
    """
    Configuración de límites de seguridad.

    Estos valores se pueden ajustar en config.yaml pero
    las reglas absolutas NO se pueden desactivar.
    """
    # Límites configurables
    max_files_per_pr: int = 10
    max_lines_changed: int = 500
    max_file_size_bytes: int = 100_000  # 100KB

    # Extensiones de archivo permitidas para modificar
    allowed_extensions: list[str] = field(default_factory=lambda: [
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".md", ".txt", ".rst",
        ".yaml", ".yml", ".toml", ".json",
        ".html", ".css", ".scss",
        ".sh", ".bash",
        ".sql",
        ".go", ".rs", ".java", ".cs", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp",
        ".gitignore", ".env.example",
    ])

    # Rutas bloqueadas (NUNCA tocar)
    blocked_paths: list[str] = field(default_factory=lambda: [
        ".env",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "secrets/",
        "credentials/",
        ".github/workflows/",
        "mikalia-app.pem",
    ])

    # Branches protegidas (NUNCA push directo)
    protected_branches: list[str] = field(default_factory=lambda: [
        "main",
        "master",
        "production",
        "release",
    ])

    # Patrones de contenido peligroso (NUNCA generar)
    dangerous_patterns: list[str] = field(default_factory=lambda: [
        "rm -rf",
        "DROP TABLE",
        "DROP DATABASE",
        "DELETE FROM",
        "format c:",
        "os.system",
        "subprocess.call",
        "eval(",
        "exec(",
        "__import__",
    ])

    # ¿Requerir tests para que un cambio sea aceptado?
    require_tests: bool = False


class SafetyGuard:
    """
    Guardián de seguridad para las acciones de Mikalia.

    Verifica que cada acción del agente esté dentro de los
    límites permitidos. Si una acción viola una regla, la
    bloquea y explica por qué.

    Este es el componente que hace la diferencia entre un
    agente útil y un agente peligroso.

    Args:
        config: Configuración de seguridad (o usa defaults).
    """

    def __init__(self, config: SafetyConfig | None = None):
        self._config = config or SafetyConfig()

    @property
    def config(self) -> SafetyConfig:
        """Acceso a la configuración de seguridad."""
        return self._config

    # ============================================================
    # Verificaciones de archivos
    # ============================================================

    def check_file_access(self, file_path: str) -> SafetyResult:
        """
        Verifica si Mikalia puede acceder/modificar un archivo.

        Reglas:
        1. No tocar archivos en rutas bloqueadas (.env, *.pem, secrets/)
        2. Solo modificar extensiones permitidas
        3. No exceder tamaño máximo de archivo

        Args:
            file_path: Ruta relativa del archivo a verificar.

        Returns:
            SafetyResult indicando si el acceso está permitido.
        """
        # Normalizar path (usar forward slashes para comparación)
        normalized = PurePosixPath(file_path.replace("\\", "/"))
        path_str = str(normalized).lower()

        # Regla 1: Verificar rutas bloqueadas
        for blocked in self._config.blocked_paths:
            blocked_lower = blocked.lower()

            # Patrón con wildcard (*.pem)
            if blocked_lower.startswith("*"):
                ext = blocked_lower[1:]  # ".pem"
                if path_str.endswith(ext):
                    return SafetyResult(
                        allowed=False,
                        reason=f"Archivo bloqueado por extensión: {blocked}",
                        severity=Severity.CRITICAL,
                        details=f"Intentó acceder a {file_path}",
                    )

            # Patrón de directorio (secrets/)
            elif blocked_lower.endswith("/"):
                if path_str.startswith(blocked_lower.rstrip("/")):
                    return SafetyResult(
                        allowed=False,
                        reason=f"Ruta bloqueada: {blocked}",
                        severity=Severity.CRITICAL,
                        details=f"Intentó acceder a {file_path}",
                    )

            # Coincidencia exacta
            elif path_str == blocked_lower or path_str.endswith("/" + blocked_lower):
                return SafetyResult(
                    allowed=False,
                    reason=f"Archivo bloqueado: {blocked}",
                    severity=Severity.CRITICAL,
                    details=f"Intentó acceder a {file_path}",
                )

        # Regla 2: Verificar extensión permitida
        extension = Path(file_path).suffix.lower()
        if extension and extension not in self._config.allowed_extensions:
            # Archivos sin extensión o con extensiones especiales
            basename = Path(file_path).name
            if basename not in (".gitignore", "Makefile", "Dockerfile", "LICENSE"):
                return SafetyResult(
                    allowed=False,
                    reason=f"Extensión no permitida: {extension}",
                    severity=Severity.BLOCKED,
                    details=f"Extensiones permitidas: {', '.join(self._config.allowed_extensions[:10])}...",
                )

        return SafetyResult(
            allowed=True,
            reason="Archivo permitido",
            severity=Severity.OK,
        )

    # ============================================================
    # Verificaciones de cambios
    # ============================================================

    def check_change_size(
        self,
        files_changed: int,
        lines_changed: int,
    ) -> SafetyResult:
        """
        Verifica que los cambios no excedan los límites.

        Si un PR toca demasiados archivos o cambia muchas líneas,
        probablemente necesita revisión humana más cuidadosa.

        Args:
            files_changed: Número de archivos modificados.
            lines_changed: Total de líneas añadidas + eliminadas.

        Returns:
            SafetyResult indicando si el tamaño está permitido.
        """
        if files_changed > self._config.max_files_per_pr:
            return SafetyResult(
                allowed=False,
                reason=(
                    f"Demasiados archivos: {files_changed} "
                    f"(máximo: {self._config.max_files_per_pr})"
                ),
                severity=Severity.BLOCKED,
                details="Considera dividir los cambios en PRs más pequeños.",
            )

        if lines_changed > self._config.max_lines_changed:
            return SafetyResult(
                allowed=False,
                reason=(
                    f"Demasiadas líneas cambiadas: {lines_changed} "
                    f"(máximo: {self._config.max_lines_changed})"
                ),
                severity=Severity.BLOCKED,
                details="Cambios muy grandes necesitan revisión humana.",
            )

        # Warning si se acerca al límite (>80%)
        if (files_changed > self._config.max_files_per_pr * 0.8
                or lines_changed > self._config.max_lines_changed * 0.8):
            return SafetyResult(
                allowed=True,
                reason="Cambios grandes pero dentro del límite",
                severity=Severity.WARNING,
                details=(
                    f"Archivos: {files_changed}/{self._config.max_files_per_pr}, "
                    f"Líneas: {lines_changed}/{self._config.max_lines_changed}"
                ),
            )

        return SafetyResult(
            allowed=True,
            reason="Tamaño de cambios aceptable",
            severity=Severity.OK,
        )

    # ============================================================
    # Verificaciones de branches
    # ============================================================

    def check_branch_push(self, branch_name: str) -> SafetyResult:
        """
        Verifica si Mikalia puede pushear a un branch.

        Regla absoluta: NUNCA push directo a branches protegidas.
        Siempre usa PRs para cambios en main/master.

        Args:
            branch_name: Nombre del branch destino.

        Returns:
            SafetyResult indicando si el push está permitido.
        """
        if branch_name in self._config.protected_branches:
            return SafetyResult(
                allowed=False,
                reason=f"Branch protegido: {branch_name}",
                severity=Severity.CRITICAL,
                details=(
                    "Mikalia nunca pushea directo a branches protegidos. "
                    "Usa PRs para proponer cambios."
                ),
            )

        # Verificar que el branch sigue la convención de Mikalia
        valid_prefixes = ("mikalia/post/", "mikalia/fix/", "mikalia/feat/", "mikalia/docs/")
        if not any(branch_name.startswith(p) for p in valid_prefixes):
            return SafetyResult(
                allowed=True,
                reason=f"Branch no sigue convención de Mikalia: {branch_name}",
                severity=Severity.WARNING,
                details=f"Prefijos esperados: {', '.join(valid_prefixes)}",
            )

        return SafetyResult(
            allowed=True,
            reason="Branch permitido",
            severity=Severity.OK,
        )

    # ============================================================
    # Verificaciones de contenido
    # ============================================================

    def check_content_safety(self, content: str) -> SafetyResult:
        """
        Verifica que el contenido generado no contenga patrones peligrosos.

        Escanea el código/texto generado por Mikalia buscando
        patrones que podrían ser destructivos o inseguros.

        Args:
            content: Código o texto generado a verificar.

        Returns:
            SafetyResult indicando si el contenido es seguro.
        """
        content_lower = content.lower()

        for pattern in self._config.dangerous_patterns:
            if pattern.lower() in content_lower:
                return SafetyResult(
                    allowed=False,
                    reason=f"Patrón peligroso detectado: '{pattern}'",
                    severity=Severity.CRITICAL,
                    details=(
                        "El código generado contiene operaciones potencialmente "
                        "destructivas. Mikalia no ejecutará este cambio."
                    ),
                )

        return SafetyResult(
            allowed=True,
            reason="Contenido seguro",
            severity=Severity.OK,
        )

    # ============================================================
    # Verificación completa de una tarea
    # ============================================================

    def validate_task(
        self,
        files_to_modify: list[str],
        target_branch: str = "main",
        total_lines: int = 0,
    ) -> SafetyResult:
        """
        Verificación completa de una tarea antes de ejecutarla.

        Combina todas las verificaciones individuales en una sola
        llamada. Útil para validar una tarea completa antes de
        empezar a ejecutarla.

        Args:
            files_to_modify: Lista de archivos que se modificarán.
            target_branch: Branch donde se hará el push/PR.
            total_lines: Total estimado de líneas a cambiar.

        Returns:
            SafetyResult con el resultado más restrictivo.
        """
        # 1. Verificar cada archivo
        for file_path in files_to_modify:
            resultado = self.check_file_access(file_path)
            if not resultado.allowed:
                logger.error(f"[SAFETY] Archivo bloqueado: {file_path} — {resultado.reason}")
                return resultado

        # 2. Verificar tamaño de cambios
        resultado = self.check_change_size(len(files_to_modify), total_lines)
        if not resultado.allowed:
            logger.error(f"[SAFETY] Cambios exceden límites — {resultado.reason}")
            return resultado

        # 3. Verificar branch (para F3 el target es un feature branch, no main)
        # En F3, validate_task se llama con el feature branch, no main
        resultado = self.check_branch_push(target_branch)
        if not resultado.allowed:
            logger.error(f"[SAFETY] Branch bloqueado: {target_branch} — {resultado.reason}")
            return resultado

        logger.info(
            f"[SAFETY] Tarea validada: {len(files_to_modify)} archivos, "
            f"~{total_lines} líneas, branch: {target_branch}"
        )
        return SafetyResult(
            allowed=True,
            reason="Tarea validada correctamente",
            severity=Severity.OK,
        )

    # ============================================================
    # Verificaciones de fuerza bruta / rate limiting
    # ============================================================

    def is_blocked_path(self, path: str) -> bool:
        """Atajo: verifica si una ruta está bloqueada."""
        return not self.check_file_access(path).allowed

    def is_allowed_extension(self, path: str) -> bool:
        """Atajo: verifica si la extensión está permitida."""
        ext = Path(path).suffix.lower()
        return ext in self._config.allowed_extensions or not ext

    def is_protected_branch(self, branch: str) -> bool:
        """Atajo: verifica si un branch está protegido."""
        return branch in self._config.protected_branches
