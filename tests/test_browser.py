"""
test_browser.py — Tests para el browser control de Mikalia.

Verifica:
- Navegacion a URLs
- Extraccion de texto
- Screenshots
- Clicks y formularios
- Manejo de errores
- Shutdown limpio

Nota: Tests que usan Playwright real se marcan con @pytest.mark.browser.
Los demas usan mocks para ser rapidos.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock


# ================================================================
# Tests con mocks (rapidos, sin browser real)
# ================================================================

class TestBrowserToolMocked:
    @pytest.fixture
    def tool(self):
        from mikalia.tools.browser import BrowserTool
        t = BrowserTool()
        # Mock del page
        t._page = MagicMock()
        t._browser = MagicMock()
        t._pw = MagicMock()
        return t

    def test_name(self, tool):
        """Tool se llama 'browser'."""
        assert tool.name == "browser"

    def test_has_parameters(self, tool):
        """Tool tiene parametros definidos."""
        params = tool.get_parameters()
        assert "action" in params["properties"]
        assert "url" in params["properties"]
        assert "selector" in params["properties"]

    def test_navigate_returns_content(self, tool):
        """Navigate retorna titulo y contenido."""
        tool._page.title.return_value = "Example Domain"
        tool._page.inner_text.return_value = "Example Domain\nThis is an example."
        tool._page.url = "https://example.com"

        result = tool.execute(action="navigate", url="https://example.com", wait_seconds=0)

        assert result.success
        assert "Example Domain" in result.output
        assert "example.com" in result.output
        tool._page.goto.assert_called_once()

    def test_navigate_truncates_long_text(self, tool):
        """Navigate trunca texto mayor a 3000 chars."""
        tool._page.title.return_value = "Big Page"
        tool._page.inner_text.return_value = "x" * 5000
        tool._page.url = "https://example.com"

        result = tool.execute(action="navigate", url="https://example.com", wait_seconds=0)

        assert result.success
        assert "[truncado]" in result.output

    def test_navigate_requires_url(self, tool):
        """Navigate sin URL retorna error."""
        result = tool.execute(action="navigate", url="", wait_seconds=0)
        assert not result.success
        assert "URL" in result.error

    def test_click_calls_page(self, tool):
        """Click llama page.click con selector."""
        tool._page.url = "https://example.com"

        result = tool.execute(action="click", selector="#submit", wait_seconds=0)

        assert result.success
        tool._page.click.assert_called_once_with("#submit", timeout=5000)

    def test_click_requires_selector(self, tool):
        """Click sin selector retorna error."""
        result = tool.execute(action="click", selector="", wait_seconds=0)
        assert not result.success

    def test_fill_calls_page(self, tool):
        """Fill llama page.fill con selector y texto."""
        result = tool.execute(
            action="fill", selector="#email", text="test@test.com", wait_seconds=0
        )

        assert result.success
        tool._page.fill.assert_called_once_with("#email", "test@test.com", timeout=5000)

    def test_fill_requires_text(self, tool):
        """Fill sin texto retorna error."""
        result = tool.execute(action="fill", selector="#email", text="", wait_seconds=0)
        assert not result.success

    def test_extract_returns_elements(self, tool):
        """Extract retorna texto de elementos."""
        mock_el1 = MagicMock()
        mock_el1.inner_text.return_value = "Item 1"
        mock_el2 = MagicMock()
        mock_el2.inner_text.return_value = "Item 2"
        tool._page.query_selector_all.return_value = [mock_el1, mock_el2]

        result = tool.execute(action="extract", selector=".item")

        assert result.success
        assert "Item 1" in result.output
        assert "Item 2" in result.output

    def test_extract_no_elements(self, tool):
        """Extract sin elementos retorna mensaje."""
        tool._page.query_selector_all.return_value = []

        result = tool.execute(action="extract", selector=".nonexistent")

        assert result.success
        assert "No se encontraron" in result.output

    def test_evaluate_runs_js(self, tool):
        """Evaluate ejecuta JavaScript."""
        tool._page.evaluate.return_value = 42

        result = tool.execute(action="evaluate", script="2 + 40")

        assert result.success
        assert "42" in result.output

    def test_screenshot_saves_file(self, tool, tmp_path):
        """Screenshot guarda archivo PNG."""
        with patch("mikalia.tools.browser.Path") as mock_path:
            mock_path.return_value = tmp_path / "data" / "screenshots"
            tool._page.url = "https://example.com"

            result = tool.execute(action="screenshot")

            assert result.success
            tool._page.screenshot.assert_called_once()

    def test_unknown_action_fails(self, tool):
        """Accion desconocida retorna error."""
        result = tool.execute(action="dance")
        assert not result.success
        assert "desconocida" in result.error

    def test_shutdown_cleans_up(self, tool):
        """Shutdown cierra page, browser y playwright."""
        page = tool._page
        browser = tool._browser
        pw = tool._pw

        tool.shutdown()

        page.close.assert_called_once()
        browser.close.assert_called_once()
        pw.stop.assert_called_once()
        assert tool._page is None
        assert tool._browser is None

    def test_to_claude_definition(self, tool):
        """to_claude_definition genera formato correcto."""
        defn = tool.to_claude_definition()
        assert defn["name"] == "browser"
        assert "navigate" in defn["description"]


# ================================================================
# Test de integracion real (requiere Playwright instalado)
# ================================================================

class TestBrowserReal:
    @pytest.fixture
    def real_tool(self):
        """BrowserTool real (con browser)."""
        from mikalia.tools.browser import BrowserTool
        tool = BrowserTool()
        yield tool
        tool.shutdown()

    def test_real_navigate(self, real_tool):
        """Navegacion real a example.com."""
        result = real_tool.execute(
            action="navigate",
            url="https://example.com",
            wait_seconds=0.5,
        )
        assert result.success
        assert "Example Domain" in result.output

    def test_real_extract(self, real_tool):
        """Extraccion real de elementos."""
        real_tool.execute(action="navigate", url="https://example.com", wait_seconds=0.5)
        result = real_tool.execute(action="extract", selector="h1")
        assert result.success
        assert "Example Domain" in result.output

    def test_real_evaluate(self, real_tool):
        """Evaluacion real de JavaScript."""
        real_tool.execute(action="navigate", url="https://example.com", wait_seconds=0.5)
        result = real_tool.execute(action="evaluate", script="document.title")
        assert result.success
        assert "Example Domain" in result.output
