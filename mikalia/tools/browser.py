"""
browser.py — Browser control tool para Mikalia.

Permite a Mikalia navegar la web como un humano: visitar paginas,
extraer texto, tomar screenshots, hacer clicks, llenar formularios.

Usa Playwright con Chromium headless. Un solo browser se reutiliza
entre llamadas para eficiencia.

Uso:
    from mikalia.tools.browser import BrowserTool
    tool = BrowserTool()
    result = tool.execute(action="navigate", url="https://example.com")
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.browser")


class BrowserTool(BaseTool):
    """
    Browser control — Mikalia's eyes on the web.

    Acciones disponibles:
    - navigate: Ir a una URL y extraer texto
    - screenshot: Capturar screenshot de la pagina
    - click: Click en un elemento (por selector CSS)
    - fill: Llenar un campo de texto
    - extract: Extraer texto de un selector especifico
    - evaluate: Ejecutar JavaScript en la pagina
    """

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._page = None

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Control a real web browser (Chromium). Navigate pages, extract "
            "text, take screenshots, click elements, fill forms. "
            "Actions: 'navigate' (go to URL, get text), 'screenshot' (capture page), "
            "'click' (click element by CSS selector), 'fill' (type in input field), "
            "'extract' (get text from specific element), 'evaluate' (run JS)."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform",
                    "enum": [
                        "navigate", "screenshot", "click",
                        "fill", "extract", "evaluate",
                    ],
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for 'navigate' action)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for click/fill/extract (e.g. '#search', '.btn')",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for 'fill' action)",
                },
                "script": {
                    "type": "string",
                    "description": "JavaScript to execute (for 'evaluate' action)",
                },
                "wait_seconds": {
                    "type": "number",
                    "description": "Seconds to wait after action (default 1)",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        url: str = "",
        selector: str = "",
        text: str = "",
        script: str = "",
        wait_seconds: float = 1.0,
        **_: Any,
    ) -> ToolResult:
        try:
            self._ensure_browser()

            if action == "navigate":
                return self._navigate(url, wait_seconds)
            elif action == "screenshot":
                return self._screenshot()
            elif action == "click":
                return self._click(selector, wait_seconds)
            elif action == "fill":
                return self._fill(selector, text, wait_seconds)
            elif action == "extract":
                return self._extract(selector)
            elif action == "evaluate":
                return self._evaluate(script)
            else:
                return ToolResult(
                    success=False,
                    error=f"Accion desconocida: '{action}'",
                )
        except Exception as e:
            logger.error(f"Browser error: {e}")
            return ToolResult(success=False, error=str(e))

    # ================================================================
    # Acciones
    # ================================================================

    def _navigate(self, url: str, wait: float) -> ToolResult:
        """Navega a una URL y retorna el texto de la pagina."""
        if not url:
            return ToolResult(success=False, error="URL requerida para navigate")

        self._page.goto(url, timeout=15000)
        time.sleep(wait)

        title = self._page.title()
        # Extraer texto visible (no HTML)
        text = self._page.inner_text("body")
        # Truncar a 3000 chars para no saturar el contexto
        if len(text) > 3000:
            text = text[:3000] + "\n... [truncado]"

        current_url = self._page.url
        return ToolResult(
            success=True,
            output=(
                f"URL: {current_url}\n"
                f"Title: {title}\n"
                f"Content:\n{text}"
            ),
        )

    def _screenshot(self) -> ToolResult:
        """Toma screenshot y retorna path del archivo."""
        screenshots_dir = Path("data/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())
        path = screenshots_dir / f"screenshot_{timestamp}.png"
        self._page.screenshot(path=str(path))

        return ToolResult(
            success=True,
            output=f"Screenshot guardado: {path}\nURL: {self._page.url}",
        )

    def _click(self, selector: str, wait: float) -> ToolResult:
        """Click en un elemento por CSS selector."""
        if not selector:
            return ToolResult(success=False, error="Selector requerido para click")

        self._page.click(selector, timeout=5000)
        time.sleep(wait)

        return ToolResult(
            success=True,
            output=f"Click en '{selector}' exitoso. URL actual: {self._page.url}",
        )

    def _fill(self, selector: str, text: str, wait: float) -> ToolResult:
        """Llena un campo de texto."""
        if not selector:
            return ToolResult(success=False, error="Selector requerido para fill")
        if not text:
            return ToolResult(success=False, error="Texto requerido para fill")

        self._page.fill(selector, text, timeout=5000)
        time.sleep(wait)

        return ToolResult(
            success=True,
            output=f"Campo '{selector}' llenado con: '{text[:50]}'",
        )

    def _extract(self, selector: str) -> ToolResult:
        """Extrae texto de un elemento especifico."""
        if not selector:
            return ToolResult(success=False, error="Selector requerido para extract")

        elements = self._page.query_selector_all(selector)
        if not elements:
            return ToolResult(
                success=True,
                output=f"No se encontraron elementos con selector '{selector}'",
            )

        texts = []
        for el in elements[:20]:  # Max 20 elementos
            t = el.inner_text()
            if t.strip():
                texts.append(t.strip())

        return ToolResult(
            success=True,
            output=f"Encontrados {len(texts)} elementos:\n" + "\n".join(texts),
        )

    def _evaluate(self, script: str) -> ToolResult:
        """Ejecuta JavaScript en la pagina."""
        if not script:
            return ToolResult(success=False, error="Script requerido para evaluate")

        result = self._page.evaluate(script)
        return ToolResult(
            success=True,
            output=f"Resultado: {result}",
        )

    # ================================================================
    # Browser lifecycle
    # ================================================================

    def _ensure_browser(self) -> None:
        """Inicia browser si no esta corriendo."""
        if self._page is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ImportError(
                "Playwright no instalado. "
                "Ejecuta: pip install playwright && python -m playwright install chromium"
            )

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        self._page = self._browser.new_page(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        logger.success("Browser Chromium iniciado (headless)")

    def shutdown(self) -> None:
        """Cierra browser y limpia recursos."""
        if self._page:
            self._page.close()
            self._page = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None
        logger.info("Browser cerrado.")
