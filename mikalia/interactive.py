"""
interactive.py — Modo interactivo de Mikalia.

En este modo, Mikalia "platica" contigo en la terminal:
te pregunta el tema, muestra un preview, y te deja decidir
si publicar, descartar, o editar.

¿Por qué un modo interactivo?
    - Más amigable que recordar flags de CLI
    - Mikalia muestra su personalidad en la conversación
    - Puedes ver el preview antes de publicar
    - Opción de editar en tu editor favorito ($EDITOR)

Flujo:
    1. Mikalia saluda y pregunta el tema
    2. Genera el post con spinner visual
    3. Muestra preview (título, primeras líneas)
    4. Pregunta: ¿Publicar? [s/n/editar]
        s → commit + push
        n → descarta
        editar → abre en $EDITOR (VS Code, vim, etc.)
    5. Si publicó, muestra resumen con URL

Uso:
    python -m mikalia interactive
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from mikalia.config import load_config
from mikalia.personality import load_personality
from mikalia.generation.client import MikaliaClient
from mikalia.generation.post_generator import PostGenerator
from mikalia.publishing.hugo_formatter import HugoFormatter
from mikalia.publishing.git_ops import GitOperations
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.interactive")
console = Console()


def run_interactive():
    """
    Ejecuta el modo interactivo completo.

    Este es el flujo principal donde Mikalia conversa con
    el usuario en la terminal.
    """
    # Saludo de Mikalia
    console.print(Panel(
        "[bold rgb(240,165,0)]🌸 ¡Hola! Soy Mikalia.[/bold rgb(240,165,0)]\n"
        "Tu agente de contenido autónomo.\n"
        "Cuéntame: ¿sobre qué quieres que escriba hoy?",
        border_style="rgb(240,165,0)",
    ))

    # Preguntar tema
    topic = Prompt.ask("\n[bold cyan]Tema[/bold cyan]")

    if not topic.strip():
        logger.error("No se proporcionó un tema. ¡Necesito saber de qué escribir!")
        return

    # Preguntar categoría (opcional)
    category = Prompt.ask(
        "[cyan]Categoría (opcional, Enter para auto)[/cyan]",
        default="",
    )

    try:
        # Cargar todo
        config = load_config()
        personality = load_personality()
        client = MikaliaClient(
            api_key=config.anthropic_api_key,
            model=config.mikalia.model,
            personality=personality,
        )

        # Generar con spinner visual
        with console.status(
            "[bold rgb(240,165,0)]🌸 Mikalia está escribiendo...[/bold rgb(240,165,0)]",
            spinner="dots",
        ):
            generator = PostGenerator(client, config)
            post = generator.generate_post(
                topic=topic,
                category=category if category else None,
            )

        # Mostrar preview
        console.print("\n")
        console.print(Panel(
            f"[bold]EN:[/bold] {post.metadata.title_en}\n"
            f"[bold]ES:[/bold] {post.metadata.title_es}\n"
            f"[bold]Tags:[/bold] {', '.join(post.metadata.tags)}\n"
            f"[bold]Review:[/bold] {'✅ Aprobado' if post.review_passed else '⚠️ Con observaciones'}",
            title="📝 Preview",
            border_style="rgb(240,165,0)",
        ))

        # Mostrar primeras líneas del contenido
        console.print("\n[bold cyan]--- Primeras líneas (EN) ---[/bold cyan]")
        lineas_en = post.content_en.split("\n")[:8]
        console.print("\n".join(lineas_en))
        console.print("[dim]...[/dim]\n")

        # Preguntar acción
        accion = Prompt.ask(
            "¿Qué hacemos?",
            choices=["publicar", "guardar", "descartar", "ver-completo"],
            default="publicar",
        )

        if accion == "publicar":
            _publish(config, post)
        elif accion == "guardar":
            _save_local(config, post)
        elif accion == "ver-completo":
            _show_full(post)
            # Después de ver completo, preguntar de nuevo
            accion2 = Prompt.ask(
                "¿Ahora qué?",
                choices=["publicar", "guardar", "descartar"],
                default="publicar",
            )
            if accion2 == "publicar":
                _publish(config, post)
            elif accion2 == "guardar":
                _save_local(config, post)
            else:
                logger.mikalia("Descartado. ¡Otra vez será!")
        else:
            logger.mikalia("Descartado. ¡Otra vez será!")

    except KeyboardInterrupt:
        console.print("\n")
        logger.mikalia("¡Hasta luego! 🌸")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


def _publish(config, post):
    """Publica el post (commit + push)."""
    formatter = HugoFormatter(config)
    formatted = formatter.format_post(post)

    with console.status("[bold green]Publicando...[/bold green]"):
        git = GitOperations(config.blog.repo_path, config)
        git.sync_repo()
        commit_hash = git.publish_post(
            formatted.files,
            post.metadata.title_en,
        )

    blog_url = f"https://mikata-ai-lab.github.io/blog/{post.metadata.slug}/"
    console.print(Panel(
        f"[bold green]¡Publicado![/bold green]\n"
        f"Commit: {commit_hash[:7]}\n"
        f"URL: {blog_url}\n"
        f"GitHub Actions se encarga del deploy (~39 segundos).",
        title="🌸 ¡Listo!",
        border_style="green",
    ))


def _save_local(config, post):
    """Guarda el post localmente sin publicar."""
    formatter = HugoFormatter(config)
    formatted = formatter.format_post(post)

    git = GitOperations(config.blog.repo_path, config)
    rutas = git.write_files_only(formatted.files)

    logger.success("Archivos guardados localmente:")
    for ruta in rutas:
        logger.info(f"  → {ruta}")


def _show_full(post):
    """Muestra el post completo en la terminal."""
    console.print("\n[bold cyan]═══ CONTENIDO COMPLETO EN ═══[/bold cyan]\n")
    console.print(post.content_en)
    console.print("\n[bold cyan]═══ CONTENIDO COMPLETO ES ═══[/bold cyan]\n")
    console.print(post.content_es)
    console.print()
