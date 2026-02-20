"""
logger.py — Logging bonito para Mikalia usando Rich + archivo.

Dual output:
- Rich console: colores y formato bonito para uso interactivo
- Archivo rotativo: logs/mikalia.log para VPS y debugging post-mortem

Uso:
    from mikalia.utils.logger import get_logger, console
    logger = get_logger("mikalia.generation")
    logger.info("Generando post...")
    logger.success("Post generado exitosamente")
    logger.error("Error al conectar con la API")
"""

from __future__ import annotations

import io
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.theme import Theme

# Fix para Windows: forzar encoding UTF-8 en stdout/stderr
# La terminal de Windows usa cp1252 por defecto, que no soporta emojis.
# Wrapeamos stdout con un TextIOWrapper que reemplaza caracteres
# no encodables en vez de crashear.
# NOTA: No aplicar si estamos en pytest (conflicto con capture system)
_in_pytest = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
if sys.platform == "win32" and not _in_pytest:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

# Tema custom de Mikalia para la consola
# Los colores coinciden con la paleta del blog (gold/amber)
mikalia_theme = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "mikalia": "bold rgb(240,165,0)",  # Gold (#f0a500)
    "step": "bold rgb(255,107,53)",    # Orange (#ff6b35)
})

# Detectar si la terminal soporta Unicode (emojis)
# Windows con cp1252 no soporta emojis — usamos ASCII alternativo
_SUPPORTS_EMOJI = sys.stdout.encoding and "utf" in sys.stdout.encoding.lower()

# Consola global — se usa en todo el proyecto
# force_terminal=True + force_jupyter=False ayuda en Windows
console = Console(theme=mikalia_theme)

# ================================================================
# File logging setup
# ================================================================

_file_logger: logging.Logger | None = None


def _setup_file_logger() -> logging.Logger:
    """Configura el logger de archivo con rotacion."""
    global _file_logger
    if _file_logger is not None:
        return _file_logger

    # No crear logs en pytest
    if _in_pytest:
        _file_logger = logging.getLogger("mikalia.null")
        _file_logger.addHandler(logging.NullHandler())
        return _file_logger

    # Crear directorio de logs
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    _file_logger = logging.getLogger("mikalia.file")
    _file_logger.setLevel(logging.DEBUG)

    # Evitar handlers duplicados
    if not _file_logger.handlers:
        handler = RotatingFileHandler(
            log_dir / "mikalia.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        _file_logger.addHandler(handler)

    return _file_logger


class MikaliaLogger:
    """
    Logger personalizado que usa Rich para output bonito + archivo para VPS.

    Cada módulo crea su propio logger con un nombre para
    identificar de dónde viene cada mensaje.

    Args:
        name: Nombre del módulo (ej: "mikalia.generation")
    """

    def __init__(self, name: str):
        self._name = name
        self._file = _setup_file_logger()

    def info(self, message: str) -> None:
        """Mensaje informativo (cyan)."""
        icon = "i " if not _SUPPORTS_EMOJI else "i  "
        console.print(f"[info]{icon}{message}[/info]")
        self._file.info(f"[{self._name}] {message}")

    def success(self, message: str) -> None:
        """Mensaje de éxito (verde)."""
        icon = "[OK]" if not _SUPPORTS_EMOJI else "[OK]"
        console.print(f"[success]{icon} {message}[/success]")
        self._file.info(f"[{self._name}] OK: {message}")

    def warning(self, message: str) -> None:
        """Mensaje de advertencia (amarillo)."""
        icon = "[!]" if not _SUPPORTS_EMOJI else "[!] "
        console.print(f"[warning]{icon} {message}[/warning]")
        self._file.warning(f"[{self._name}] {message}")

    def error(self, message: str) -> None:
        """Mensaje de error (rojo)."""
        icon = "[X]" if not _SUPPORTS_EMOJI else "[X]"
        console.print(f"[error]{icon} {message}[/error]")
        self._file.error(f"[{self._name}] {message}")

    def mikalia(self, message: str) -> None:
        """Mensaje con la voz de Mikalia (dorado)."""
        icon = "[Mikalia]" if not _SUPPORTS_EMOJI else "[Mikalia]"
        console.print(f"[mikalia]{icon} {message}[/mikalia]")
        self._file.info(f"[{self._name}] [Mikalia] {message}")

    def step(self, number: int, total: int, message: str) -> None:
        """Mensaje de paso en un proceso (naranja)."""
        console.print(f"[step]  [{number}/{total}] {message}[/step]")
        self._file.info(f"[{self._name}] [{number}/{total}] {message}")


def get_logger(name: str = "mikalia") -> MikaliaLogger:
    """
    Obtiene un logger para el módulo especificado.

    Args:
        name: Nombre del módulo.

    Returns:
        MikaliaLogger configurado.

    Ejemplo:
        logger = get_logger("mikalia.generation")
        logger.info("Iniciando generación...")
    """
    return MikaliaLogger(name)
