"""
personality.py — Carga la personalidad de Mikalia desde MIKALIA.md.

LEGACY: Usado por comandos F1-F3 (post, interactive, agent, chat).
Los comandos Core (chat --core, core) usan identity.yaml via ContextBuilder.
Cuando se migren todos los comandos a Core, este modulo se puede eliminar.

Uso:
    from mikalia.personality import load_personality
    personality = load_personality()
    print(personality.system_prompt)  # Contenido completo de MIKALIA.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Personality:
    """
    Representa la personalidad cargada de Mikalia.

    Attributes:
        system_prompt: Contenido completo de MIKALIA.md (se usa como system prompt)
        name: Nombre del agente ("Mikalia")
        signature: Firma que va al final de cada post
        source_path: Ruta del archivo desde donde se cargó
    """
    system_prompt: str
    name: str = "Mikalia"
    signature: str = "— Mikalia 🌸"
    source_path: Path | None = None


def _find_personality_file() -> Path:
    """
    Busca MIKALIA.md en ubicaciones conocidas.

    Orden de búsqueda:
    1. Directorio actual
    2. Directorio padre (por si se ejecuta desde mikalia/)
    3. Directorio del proyecto (buscando hacia arriba)

    ¿Por qué buscar en múltiples lugares?
    Porque Mikalia puede ejecutarse desde diferentes directorios:
    - Desde la raíz del proyecto: python -m mikalia
    - Desde un subdirectorio: cd mikalia && python cli.py
    - Desde GitHub Actions: el working directory puede variar
    """
    # Posibles nombres del archivo
    nombres = ["MIKALIA.md", "mikalia.md"]

    # Buscar desde el directorio actual hacia arriba
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        for nombre in nombres:
            archivo = parent / nombre
            if archivo.exists():
                return archivo

    # Si no se encuentra, lanzar error descriptivo
    raise FileNotFoundError(
        "No se encontró MIKALIA.md en ninguna ubicación.\n"
        "Asegúrate de que el archivo existe en la raíz del proyecto.\n"
        f"Directorio actual: {current}"
    )


def load_personality(path: Path | None = None) -> Personality:
    """
    Carga la personalidad de Mikalia desde MIKALIA.md.

    Args:
        path: Ruta explícita al archivo. Si es None, busca automáticamente.

    Returns:
        Personality con el system prompt y metadata.

    Raises:
        FileNotFoundError: Si no se encuentra MIKALIA.md.
        UnicodeDecodeError: Si el archivo no es UTF-8 válido.

    Ejemplo:
        # Carga automática (busca MIKALIA.md)
        personality = load_personality()

        # Carga explícita
        personality = load_personality(Path("./custom-personality.md"))
    """
    # Encontrar el archivo
    if path is None:
        path = _find_personality_file()
    elif not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path}")

    # Leer el contenido
    contenido = path.read_text(encoding="utf-8").strip()

    # Validar que no esté vacío
    if not contenido:
        raise ValueError(
            f"MIKALIA.md está vacío: {path}\n"
            "El archivo de personalidad debe contener el system prompt."
        )

    return Personality(
        system_prompt=contenido,
        source_path=path,
    )
