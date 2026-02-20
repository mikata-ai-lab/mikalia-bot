"""
cli.py — Punto de entrada principal del bot Mikalia.

Este archivo maneja todos los comandos CLI usando Click.

¿Por qué Click en vez de argparse?
    - Sintaxis más limpia con decoradores
    - Subcomandos nativos (post, interactive, config, health)
    - Colores y formato de ayuda mejores
    - Integración con Rich para output bonito
    - Validación de parámetros automática

Comandos disponibles:
    python -m mikalia post --topic "Mi tema"     → Genera y publica post
    python -m mikalia post --topic "X" --dry-run → Genera sin publicar
    python -m mikalia post --topic "X" --preview → Muestra en terminal
    python -m mikalia post --topic "X" --repo "owner/repo" → Post basado en repo [F2]
    python -m mikalia post --topic "X" --doc "path/file.md" → Post basado en doc [F2]
    python -m mikalia interactive                 → Modo interactivo
    python -m mikalia config --show               → Muestra configuración
    python -m mikalia config --validate           → Valida configuración
    python -m mikalia health                      → Verifica conexiones

Uso:
    # Desde línea de comandos:
    python -m mikalia post --topic "Building AI Agents"

    # Desde código (testing):
    from mikalia.cli import main
    main(["post", "--topic", "Testing"])
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mikalia.config import load_config
from mikalia.personality import load_personality
from mikalia.generation.client import MikaliaClient
from mikalia.generation.post_generator import PostGenerator
from mikalia.publishing.hugo_formatter import HugoFormatter
from mikalia.publishing.git_ops import GitOperations
from mikalia.notifications.notifier import Notifier, Event
from mikalia.notifications.telegram import TelegramChannel
from mikalia.utils.logger import get_logger, console as rich_console

logger = get_logger("mikalia.cli")

# Banner de Mikalia para la terminal
# Nota: Usamos caracteres ASCII simples porque la terminal de Windows
# (cp1252) no soporta box-drawing Unicode correctamente
BANNER = """
[bold rgb(240,165,0)]  ========================================
  MIKALIA BOT -- Mikata AI Lab
  Tu agente autonomo de contenido
  ========================================[/bold rgb(240,165,0)]"""


@click.group()
@click.version_option(version="1.0.0", prog_name="Mikalia Bot")
def main():
    """* Mikalia Bot — Agente autónomo de IA para Mikata AI Lab."""
    pass


@main.command()
@click.option(
    "--topic", "-t",
    required=True,
    help="Tema del post (ej: 'Building AI Agents with Python')"
)
@click.option(
    "--category", "-c",
    default=None,
    help="Categoría del post (ej: 'ai', 'tutorials')"
)
@click.option(
    "--tags",
    default=None,
    help="Tags separados por coma (ej: 'ai,claude,agents')"
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Genera y guarda local, NO pushea a GitHub"
)
@click.option(
    "--preview",
    is_flag=True,
    default=False,
    help="Muestra en terminal, NO guarda ni pushea"
)
@click.option(
    "--repo", "-r",
    default=None,
    help="[F2] Repo para contexto (ej: 'owner/repo' o ruta local)"
)
@click.option(
    "--doc", "-d",
    default=None,
    help="[F2] Documento para contexto (ej: 'docs/architecture.md')"
)
def post(
    topic: str,
    category: str | None,
    tags: str | None,
    dry_run: bool,
    preview: bool,
    repo: str | None,
    doc: str | None,
):
    """📝 Genera y publica un post bilingüe."""
    rich_console.print(BANNER)
    logger.mikalia(f"¡Hora de escribir! Tema: {topic}")

    # Parsear tags si se proporcionaron
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    try:
        # Cargar configuración y personalidad
        config = load_config()
        personality = load_personality()

        # Crear cliente de API
        client = MikaliaClient(
            api_key=config.anthropic_api_key,
            model=config.mikalia.model,
            personality=personality,
        )

        # [F2] Obtener contexto de repo o documento si se especificó
        context = None
        if repo:
            from mikalia.generation.repo_analyzer import RepoAnalyzer
            logger.info(f"Analizando repo: {repo}")
            analyzer = RepoAnalyzer()
            repo_context = analyzer.analyze(repo, focus_topic=topic)
            context = repo_context.to_prompt()
            logger.success(f"Contexto extraído: {len(context)} chars")
        elif doc:
            from mikalia.generation.doc_analyzer import DocAnalyzer
            logger.info(f"Analizando documento: {doc}")
            analyzer = DocAnalyzer()
            doc_context = analyzer.analyze(doc, focus_topic=topic)
            context = doc_context.to_prompt()
            logger.success(f"Contexto extraído: {len(context)} chars")

        # Generar post
        generator = PostGenerator(client, config)
        generated_post = generator.generate_post(
            topic=topic,
            category=category,
            tags=tag_list,
            context=context,
        )

        # Formatear para Hugo
        formatter = HugoFormatter(config)
        formatted = formatter.format_post(generated_post)

        # === MODO PREVIEW: solo mostrar en terminal ===
        if preview:
            _show_preview(generated_post, formatted)
            return

        # === MODO DRY-RUN: guardar local sin push ===
        if dry_run:
            git = GitOperations(config.blog.repo_path, config)
            rutas = git.write_files_only(formatted.files)
            logger.success("Archivos guardados localmente (dry-run):")
            for ruta in rutas:
                logger.info(f"  → {ruta}")
            return

        # === MODO NORMAL: guardar + commit + push ===
        git = GitOperations(config.blog.repo_path, config)
        git.sync_repo()
        commit_hash = git.publish_post(
            formatted.files,
            generated_post.metadata.title_en,
        )

        # Notificar por Telegram
        _notify_publication(config, generated_post)

        # Resumen final
        _show_summary(generated_post, commit_hash)

    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        _notify_error(str(e))
        sys.exit(1)


@main.command()
def interactive():
    """* Modo interactivo — Mikalia te pregunta el tema."""
    rich_console.print(BANNER)

    # Importar aquí para evitar circular imports
    from mikalia.interactive import run_interactive
    run_interactive()


@main.command()
@click.option(
    "--repo", "-r",
    required=True,
    help="Repo objetivo (ej: 'owner/repo' o ruta local)"
)
@click.option(
    "--task", "-t",
    required=True,
    help="Tarea a ejecutar (ej: 'Add error handling to API calls')"
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Genera cambios sin crear PR"
)
def agent(repo: str, task: str, dry_run: bool):
    """[F3] Agente de código — Mikalia propone cambios y crea PRs."""
    rich_console.print(BANNER)
    logger.mikalia(f"Modo agente: {task}")

    try:
        config = load_config()
        personality = load_personality()

        client = MikaliaClient(
            api_key=config.anthropic_api_key,
            model=config.mikalia.model,
            personality=personality,
        )

        from mikalia.agent.code_agent import CodeAgent
        code_agent = CodeAgent(client, config)
        result = code_agent.execute_task(
            repo=repo,
            task=task,
            dry_run=dry_run,
        )

        if result.success:
            rich_console.print(Panel(
                f"[bold]Tarea:[/bold] {task}\n"
                f"[bold]Archivos:[/bold] {len(result.changes)}\n"
                f"[bold]PR:[/bold] {result.pr.url if result.pr and result.pr.number else 'N/A (dry-run)'}\n"
                f"[bold]Resumen:[/bold]\n{result.summary}",
                title="[OK] Agente completado",
                border_style="green",
            ))

            # Notificar por Telegram si hay PR
            if result.pr and result.pr.number and config.telegram.enabled:
                notifier = _build_notifier(config)
                from mikalia.notifications.notifier import Event
                notifier.notify(Event.PR_CREATED, {
                    "title": task,
                    "pr_url": result.pr.url,
                })
        else:
            rich_console.print(Panel(
                f"[bold]Tarea:[/bold] {task}\n"
                f"[bold]Error:[/bold] {result.error}",
                title="[X] Agente falló",
                border_style="red",
            ))
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error en agente: {e}")
        sys.exit(1)


@main.command()
@click.option(
    "--core",
    is_flag=True,
    default=False,
    help="Usar Mikalia Core (memoria + tools + self-improvement)",
)
def chat(core: bool):
    """* Modo chat — Habla con Mikalia por Telegram."""
    rich_console.print(BANNER)

    bot = None
    try:
        cfg = load_config()

        if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
            logger.error(
                "Telegram no configurado. Necesitas TELEGRAM_BOT_TOKEN y "
                "TELEGRAM_CHAT_ID en tu .env"
            )
            sys.exit(1)

        from mikalia.notifications.telegram_listener import TelegramListener

        if core:
            logger.mikalia("Modo chat CORE activado. Memoria + Tools + Self-improvement.")

            from mikalia.core.agent import MikaliaAgent
            from mikalia.notifications.telegram_listener import MikaliaCoreBot

            agent = MikaliaAgent()

            # Crear listener primero para pasar typing indicator al bot
            listener = TelegramListener(
                bot_token=cfg.telegram_bot_token,
                chat_id=cfg.telegram_chat_id,
            )
            bot = MikaliaCoreBot(agent, listener=listener)
            listener._on_message = bot.handle_message

            # Iniciar scheduler
            from mikalia.core.scheduler import MikaliaScheduler
            scheduler = MikaliaScheduler(
                memory=agent.memory,
                send_fn=listener.send,
                check_interval=60,
            )
            scheduler.start()

            mode_title = "Chat Core activo"
            mode_desc = (
                "Mikalia Core v2.0 escuchando en Telegram.\n"
                "18 tools, memoria, scheduler, y aprendizaje activos.\n"
                "Comandos: /brief /goals /facts /help\n\n"
                "Presiona Ctrl+C para detener."
            )
        else:
            logger.mikalia("Modo chat basico activado. Escuchando en Telegram...")

            personality = load_personality()
            client = MikaliaClient(
                api_key=cfg.anthropic_api_key,
                model=cfg.mikalia.model,
                personality=personality,
            )

            from mikalia.notifications.telegram_listener import MikaliaChatBot

            bot = MikaliaChatBot(cfg, client)

            mode_title = "Chat activo"
            mode_desc = (
                "Mikalia esta escuchando en Telegram.\n"
                "Escribele a tu bot para chatear.\n\n"
                "Presiona Ctrl+C para detener."
            )

        if not core:
            listener = TelegramListener(
                bot_token=cfg.telegram_bot_token,
                chat_id=cfg.telegram_chat_id,
                on_message=bot.handle_message,
            )

        rich_console.print(Panel(
            mode_desc,
            title=mode_title,
            border_style="rgb(240,165,0)",
        ))

        listener.listen()

    except KeyboardInterrupt:
        if core:
            if 'scheduler' in locals():
                scheduler.stop()
            if bot:
                bot.shutdown()
        logger.info("Chat detenido")
    except Exception as e:
        if core:
            if 'scheduler' in locals():
                scheduler.stop()
            if bot:
                bot.shutdown()
        logger.error(f"Error en chat: {e}")
        sys.exit(1)


@main.command()
def core():
    """Mikalia Core — Agente autonomo con memoria y tools."""
    from rich.prompt import Prompt

    rich_console.print(BANNER)
    logger.mikalia("Mikalia Core activado. Escribe /quit para salir.")

    try:
        from mikalia.core.agent import MikaliaAgent

        agent = MikaliaAgent()
        session_id = None

        rich_console.print(Panel(
            "Soy Mikalia Core. Tengo memoria, herramientas, y un corazon.\n"
            "Escribe lo que necesites. Yo me encargo.\n\n"
            "Comandos: /quit /goals /facts",
            title="Mikalia Core v2.0",
            border_style="rgb(240,165,0)",
        ))

        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]Tu[/bold cyan]")
            except (KeyboardInterrupt, EOFError):
                break

            if not user_input.strip():
                continue

            cmd = user_input.strip().lower()

            if cmd == "/quit":
                break

            if cmd == "/goals":
                _show_goals(agent)
                continue

            if cmd == "/facts":
                _show_facts(agent)
                continue

            with rich_console.status(
                "[bold rgb(240,165,0)]Mikalia esta pensando...[/bold rgb(240,165,0)]",
                spinner="dots",
            ):
                response = agent.process_message(
                    message=user_input,
                    channel="cli",
                    session_id=session_id,
                )
                session_id = agent.session_id

            rich_console.print(
                f"\n[bold rgb(240,165,0)]Mikalia:[/bold rgb(240,165,0)] {response}"
            )

    except KeyboardInterrupt:
        pass

    logger.mikalia("Hasta luego, Mikata-kun. Cuida tu salud.")


def _show_goals(agent):
    """Muestra goals activos desde la memoria."""
    goals = agent.memory.get_active_goals()
    tabla = Table(title="Goals Activos")
    tabla.add_column("ID", style="cyan")
    tabla.add_column("Proyecto", style="green")
    tabla.add_column("Titulo")
    tabla.add_column("Progreso", style="rgb(240,165,0)")
    tabla.add_column("Prioridad")
    for g in goals:
        tabla.add_row(
            str(g["id"]), g["project"], g["title"],
            f"{g['progress']}%", g.get("priority", "")
        )
    rich_console.print(tabla)


def _show_facts(agent):
    """Muestra facts conocidos desde la memoria."""
    facts = agent.memory.get_facts()
    tabla = Table(title="Facts Conocidos")
    tabla.add_column("Categoria", style="cyan")
    tabla.add_column("Sujeto", style="green")
    tabla.add_column("Fact")
    for f in facts[:15]:
        tabla.add_row(f["category"], f["subject"], f["fact"][:80])
    rich_console.print(tabla)


@main.command()
@click.option("--show", is_flag=True, help="Muestra la configuración actual")
@click.option("--validate", is_flag=True, help="Valida la configuración")
def config(show: bool, validate: bool):
    """⚙️ Gestiona la configuración de Mikalia."""
    cfg = load_config()

    if show:
        tabla = Table(title="Configuración de Mikalia")
        tabla.add_column("Parámetro", style="cyan")
        tabla.add_column("Valor", style="green")

        tabla.add_row("Modelo", cfg.mikalia.model)
        tabla.add_row("Max tokens", str(cfg.mikalia.max_tokens))
        tabla.add_row("Temperatura (gen)", str(cfg.mikalia.generation_temperature))
        tabla.add_row("Temperatura (review)", str(cfg.mikalia.review_temperature))
        tabla.add_row("Blog repo", cfg.blog.repo_path or "(no configurado)")
        tabla.add_row("GitHub org", cfg.github.org)
        tabla.add_row("Telegram", "[OK] Activo" if cfg.telegram.enabled else "[X] Inactivo")
        tabla.add_row("API Key", "[OK] Configurada" if cfg.anthropic_api_key else "[X] Falta")
        tabla.add_row("GitHub App", "[OK] Configurada" if cfg.github_app_id else "[X] Falta")

        rich_console.print(tabla)

    if validate:
        _validate_config(cfg)


@main.command()
def health():
    """🏥 Verifica que todas las conexiones funcionen."""
    rich_console.print(BANNER)
    logger.mikalia("Verificando estado de salud...")

    cfg = load_config()
    errores = []

    # 1. API Key de Anthropic
    if cfg.anthropic_api_key:
        logger.success("Anthropic API Key: configurada")
    else:
        errores.append("ANTHROPIC_API_KEY no configurada")
        logger.error("Anthropic API Key: NO configurada")

    # 2. MIKALIA.md
    try:
        personality = load_personality()
        logger.success(f"MIKALIA.md: cargado ({len(personality.system_prompt)} chars)")
    except FileNotFoundError:
        errores.append("MIKALIA.md no encontrado")
        logger.error("MIKALIA.md: NO encontrado")

    # 3. Blog repo
    if cfg.blog.repo_path:
        from pathlib import Path
        if Path(cfg.blog.repo_path).exists():
            logger.success(f"Blog repo: {cfg.blog.repo_path}")
        else:
            errores.append(f"Blog repo no existe: {cfg.blog.repo_path}")
            logger.error(f"Blog repo: NO existe ({cfg.blog.repo_path})")
    else:
        errores.append("BLOG_REPO_PATH no configurado")
        logger.warning("Blog repo: NO configurado")

    # 4. GitHub App
    if cfg.github_app_id:
        logger.success("GitHub App: configurada")
    else:
        logger.warning("GitHub App: NO configurada (opcional para F1)")

    # 5. Telegram
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        logger.success("Telegram: configurado")
    else:
        logger.warning("Telegram: NO configurado (opcional)")

    # Resumen
    if errores:
        rich_console.print(
            Panel(
                "\n".join(f"[X] {e}" for e in errores),
                title="Problemas encontrados",
                border_style="red",
            )
        )
    else:
        rich_console.print(
            Panel(
                "[OK] Todo funcionando correctamente",
                title="Estado de salud",
                border_style="green",
            )
        )


# ============================================================
# Funciones auxiliares (privadas)
# ============================================================

def _show_preview(post, formatted):
    """Muestra preview del post en la terminal."""
    rich_console.print(Panel(
        f"[bold]EN:[/bold] {post.metadata.title_en}\n"
        f"[bold]ES:[/bold] {post.metadata.title_es}\n"
        f"[bold]Tags:[/bold] {', '.join(post.metadata.tags)}\n"
        f"[bold]Category:[/bold] {post.metadata.category}\n"
        f"[bold]Slug:[/bold] {post.metadata.slug}\n"
        f"[bold]Review:[/bold] {'[OK] Aprobado' if post.review_passed else '[!] No aprobado'}",
        title="📝 Preview del Post",
        border_style="rgb(240,165,0)",
    ))

    rich_console.print("\n[bold cyan]--- Contenido EN (primeras 500 chars) ---[/bold cyan]")
    rich_console.print(post.content_en[:500] + "...")
    rich_console.print("\n[bold cyan]--- Contenido ES (primeras 500 chars) ---[/bold cyan]")
    rich_console.print(post.content_es[:500] + "...")


def _show_summary(post, commit_hash):
    """Muestra resumen después de publicar."""
    blog_url = f"https://mikata-ai-lab.github.io/blog/{post.metadata.slug}/"
    rich_console.print(Panel(
        f"[bold]Título EN:[/bold] {post.metadata.title_en}\n"
        f"[bold]Título ES:[/bold] {post.metadata.title_es}\n"
        f"[bold]Commit:[/bold] {commit_hash[:7]}\n"
        f"[bold]URL:[/bold] {blog_url}\n"
        f"[bold]Review:[/bold] {'[OK] Aprobado' if post.review_passed else '[!] Con advertencia'}\n"
        f"[bold]Iteraciones:[/bold] {post.review_iterations}",
        title="* ¡Post Publicado!",
        border_style="green",
    ))


def _notify_publication(config, post):
    """Envía notificación de post publicado."""
    if not config.telegram.enabled:
        return

    notifier = _build_notifier(config)
    blog_url = f"https://mikata-ai-lab.github.io/blog/{post.metadata.slug}/"
    notifier.notify(Event.POST_PUBLISHED, {
        "title": post.metadata.title_en,
        "url": blog_url,
    })


def _notify_error(error_message: str):
    """Envía notificación de error."""
    try:
        config = load_config()
        if not config.telegram.enabled:
            return
        notifier = _build_notifier(config)
        notifier.notify(Event.ERROR, {"error_message": error_message})
    except Exception:
        pass  # Si la notificación de error falla, no hacer nada


def _build_notifier(config) -> Notifier:
    """Construye un Notifier con los canales configurados."""
    channels = []
    if config.telegram_bot_token and config.telegram_chat_id:
        channels.append(TelegramChannel(
            bot_token=config.telegram_bot_token,
            chat_id=config.telegram_chat_id,
        ))
    return Notifier(
        channels=channels,
        enabled_events=config.telegram.notify_on,
    )


def _validate_config(cfg):
    """Valida la configuración y muestra resultado."""
    problemas = []

    if not cfg.anthropic_api_key:
        problemas.append("ANTHROPIC_API_KEY no configurada en .env")
    if not cfg.blog.repo_path or cfg.blog.repo_path.startswith("$"):
        problemas.append("BLOG_REPO_PATH no configurada en .env")

    if problemas:
        for p in problemas:
            logger.error(p)
    else:
        logger.success("Configuración válida")


if __name__ == "__main__":
    main()
