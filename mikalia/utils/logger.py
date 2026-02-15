"""
logger.py — Logging bonito para Mikalia usando Rich.

Rich es una librería de Python que hace que la terminal se vea
increíble: colores, spinners, tablas, progress bars, etc.

¿Por qué Rich y no logging estándar?
    - logging estándar es funcional pero feo
    - Rich hace que debugging sea agradable
    - Los spinners dan feedback visual durante operaciones largas
    - Las tablas organizan la información claramente

Uso:
    from mikalia.utils.logger import get_logger, console
    logger = get_logger("mikalia.generation")
    logger.info("Generando post...")
    logger.success("Post generado exitosamente")
    logger.error("Error al conectar con la API")
"""

from __future__ import annotations

import io
import sys

from rich.console import Console
from rich.theme import Theme

# Fix para Windows: forzar encoding UTF-8 en stdout/stderr
# La terminal de Windows usa cp1252 por defecto, que no soporta emojis.
# Wrapeamos stdout con un TextIOWrapper que reemplaza caracteres
# no encodables en vez de crashear.
if sys.platform == "win32":
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


class MikaliaLogger:
    """
    Logger personalizado que usa Rich para output bonito.

    Cada módulo crea su propio logger con un nombre para
    identificar de dónde viene cada mensaje.

    Args:
        name: Nombre del módulo (ej: "mikalia.generation")
    """

    def __init__(self, name: str):
        self._name = name

    def info(self, message: str) -> None:
        """Mensaje informativo (cyan)."""
        icon = "i " if not _SUPPORTS_EMOJI else "i  "
        console.print(f"[info]{icon}{message}[/info]")

    def success(self, message: str) -> None:
        """Mensaje de éxito (verde)."""
        icon = "[OK]" if not _SUPPORTS_EMOJI else "[OK]"
        console.print(f"[success]{icon} {message}[/success]")

    def warning(self, message: str) -> None:
        """Mensaje de advertencia (amarillo)."""
        icon = "[!]" if not _SUPPORTS_EMOJI else "[!] "
        console.print(f"[warning]{icon} {message}[/warning]")

    def error(self, message: str) -> None:
        """Mensaje de error (rojo)."""
        icon = "[X]" if not _SUPPORTS_EMOJI else "[X]"
        console.print(f"[error]{icon} {message}[/error]")

    def mikalia(self, message: str) -> None:
        """Mensaje con la voz de Mikalia (dorado)."""
        icon = "[Mikalia]" if not _SUPPORTS_EMOJI else "[Mikalia]"
        console.print(f"[mikalia]{icon} {message}[/mikalia]")

    def step(self, number: int, total: int, message: str) -> None:
        """Mensaje de paso en un proceso (naranja)."""
        console.print(f"[step]  [{number}/{total}] {message}[/step]")


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
