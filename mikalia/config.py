"""
config.py — Carga y gestiona la configuración de Mikalia Bot.

Este archivo es el "cerebro administrativo" de Mikalia. Se encarga de:
1. Cargar config.yaml (configuración general)
2. Cargar .env (secretos: API keys, tokens)
3. Resolver variables de entorno en los valores de config
4. Validar que toda la configuración esté completa

¿Por qué separar config.yaml de .env?
    - config.yaml: Valores que SÍ se suben a Git (públicos, no sensibles)
    - .env: Valores que NUNCA se suben a Git (API keys, tokens, paths locales)

¿Por qué no usar solo variables de entorno?
    - config.yaml es más legible y organizado
    - Permite valores anidados (mikalia.model, blog.repo_path, etc.)
    - Fácil de versionar y revisar en pull requests

Uso:
    from mikalia.config import load_config
    config = load_config()
    print(config.mikalia.model)  # "claude-sonnet-4-5-20250929"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


# ============================================================
# Dataclasses de configuración
# ============================================================
# Usamos dataclasses para tener autocompletado y type safety.
# Cada sección de config.yaml tiene su propia dataclass.
# ============================================================

@dataclass
class MikaliaConfig:
    """Configuración del modelo y generación de contenido."""
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4096
    generation_temperature: float = 0.7
    review_temperature: float = 0.3
    max_review_iterations: int = 2


@dataclass
class BlogConfig:
    """Configuración del blog Hugo."""
    repo_path: str = ""
    content_base: str = "content/blog"
    en_filename: str = "index.md"
    es_filename: str = "index.es.md"
    author: str = "Mikalia"
    timezone: str = "America/Monterrey"
    categories: list[str] = field(default_factory=lambda: [
        "ai", "dev-journal", "tutorials",
        "project-updates", "thoughts", "technical", "stories"
    ])


@dataclass
class GitConfig:
    """Configuración de Git."""
    default_branch: str = "main"
    commit_prefix: str = "✨"
    branch_prefixes: dict[str, str] = field(default_factory=lambda: {
        "post": "mikalia/post",
        "fix": "mikalia/fix",
        "feat": "mikalia/feat",
        "docs": "mikalia/docs",
    })


@dataclass
class GitHubConfig:
    """Configuración de GitHub."""
    org: str = "mikata-ai-lab"
    blog_repo: str = "mikata-ai-lab.github.io"
    pr_labels: dict[str, list[str]] = field(default_factory=lambda: {
        "post": ["content", "blog", "mikalia-authored"],
        "fix": ["bugfix", "mikalia-authored"],
        "feat": ["enhancement", "mikalia-authored"],
        "docs": ["documentation", "mikalia-authored"],
    })


@dataclass
class TelegramConfig:
    """Configuración de Telegram."""
    enabled: bool = False
    notify_on: list[str] = field(default_factory=lambda: [
        "post_published", "pr_created", "review_needed", "error"
    ])


@dataclass
class NotificationsConfig:
    """Templates de mensajes de notificación."""
    post_published: str = "🌸 ¡Nuevo post publicado!\n📝 {title}\n🔗 {url}"
    pr_created: str = "🔀 PR creado por Mikalia\n📝 {title}\n🔗 {pr_url}"
    review_needed: str = "👀 Mikalia necesita tu aprobación\n📝 {title}\n🔗 {pr_url}"
    error: str = "⚠️ Error en Mikalia\n❌ {error_message}"


@dataclass
class AppConfig:
    """Configuración completa de la aplicación."""
    mikalia: MikaliaConfig = field(default_factory=MikaliaConfig)
    blog: BlogConfig = field(default_factory=BlogConfig)
    git: GitConfig = field(default_factory=GitConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)

    # Valores del .env (no están en config.yaml)
    anthropic_api_key: str = ""
    github_app_id: str = ""
    github_app_private_key_path: str = ""
    github_app_installation_id: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


# ============================================================
# Funciones de carga
# ============================================================

def _resolve_env_vars(value: str) -> str:
    """
    Resuelve variables de entorno en un string.

    Ejemplo:
        "${BLOG_REPO_PATH}" → "/home/user/blog"
        "${HOME}/.mikalia"  → "/home/user/.mikalia"

    ¿Por qué? Porque config.yaml puede referenciar valores del .env
    usando la sintaxis ${VARIABLE}. Esto permite que el mismo config.yaml
    funcione en diferentes máquinas sin modificarlo.
    """
    # Patrón: ${NOMBRE_VARIABLE}
    patron = re.compile(r"\$\{(\w+)\}")

    def reemplazar(match: re.Match) -> str:
        nombre_var = match.group(1)
        return os.environ.get(nombre_var, match.group(0))

    return patron.sub(reemplazar, value)


def _resolve_env_recursive(data: Any) -> Any:
    """
    Resuelve variables de entorno recursivamente en un dict/list.

    Recorre toda la estructura de datos del YAML y reemplaza
    cualquier ${VARIABLE} con su valor del entorno.
    """
    if isinstance(data, str):
        return _resolve_env_vars(data)
    elif isinstance(data, dict):
        return {k: _resolve_env_recursive(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_env_recursive(item) for item in data]
    return data


def _dict_to_dataclass(data: dict, cls: type) -> Any:
    """
    Convierte un diccionario a una dataclass, ignorando keys desconocidas.

    ¿Por qué no usar directamente cls(**data)?
    Porque el YAML podría tener keys que no existen en la dataclass
    (por ejemplo, si alguien agrega un campo nuevo al YAML pero no
    actualiza el código). En vez de explotar, simplemente lo ignoramos.
    """
    # Obtener los campos válidos de la dataclass
    campos_validos = {f.name for f in cls.__dataclass_fields__.values()}
    # Filtrar solo los campos que existen en la dataclass
    datos_filtrados = {k: v for k, v in data.items() if k in campos_validos}
    return cls(**datos_filtrados)


def _find_config_dir() -> Path:
    """
    Encuentra el directorio raíz del proyecto (donde está config.yaml).

    Busca hacia arriba desde el directorio actual hasta encontrar
    config.yaml. Esto permite ejecutar Mikalia desde cualquier
    subdirectorio del proyecto.
    """
    # Primero intentar el directorio actual
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / "config.yaml").exists():
            return parent
    # Si no lo encuentra, usar el directorio actual
    return current


def load_config(config_path: Path | None = None) -> AppConfig:
    """
    Carga la configuración completa de Mikalia Bot.

    Pasos:
    1. Carga .env para tener las variables de entorno disponibles
    2. Lee config.yaml
    3. Resuelve ${VARIABLES} en los valores del YAML
    4. Convierte cada sección a su dataclass correspondiente
    5. Agrega los valores del .env que no están en el YAML

    Args:
        config_path: Ruta al config.yaml. Si es None, busca automáticamente.

    Returns:
        AppConfig con toda la configuración lista para usar.
    """
    # Paso 1: Cargar .env
    proyecto_dir = _find_config_dir()
    env_path = proyecto_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Paso 2: Leer config.yaml
    if config_path is None:
        config_path = proyecto_dir / "config.yaml"

    if not config_path.exists():
        # Si no hay config.yaml, usar valores por defecto
        return AppConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}

    # Paso 3: Resolver variables de entorno
    config_resuelto = _resolve_env_recursive(raw_config)

    # Paso 4: Convertir cada sección a su dataclass
    app_config = AppConfig(
        mikalia=_dict_to_dataclass(
            config_resuelto.get("mikalia", {}), MikaliaConfig
        ),
        blog=_dict_to_dataclass(
            config_resuelto.get("blog", {}), BlogConfig
        ),
        git=_dict_to_dataclass(
            config_resuelto.get("git", {}), GitConfig
        ),
        github=_dict_to_dataclass(
            config_resuelto.get("github", {}), GitHubConfig
        ),
        telegram=_dict_to_dataclass(
            config_resuelto.get("telegram", {}), TelegramConfig
        ),
        notifications=_dict_to_dataclass(
            config_resuelto.get("notifications", {}), NotificationsConfig
        ),
    )

    # Paso 5: Agregar valores del .env
    app_config.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    app_config.github_app_id = os.environ.get("GITHUB_APP_ID", "")
    app_config.github_app_private_key_path = os.environ.get(
        "GITHUB_APP_PRIVATE_KEY_PATH", ""
    )
    app_config.github_app_installation_id = os.environ.get(
        "GITHUB_APP_INSTALLATION_ID", ""
    )
    app_config.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    app_config.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    return app_config
