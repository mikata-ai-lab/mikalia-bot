"""
test_telegram_format.py — Tests para la conversion markdown → Telegram HTML.
"""

from __future__ import annotations

from mikalia.notifications.telegram_listener import _markdown_to_telegram


class TestMarkdownToTelegram:
    def test_bold(self):
        assert "<b>hola</b>" in _markdown_to_telegram("**hola**")

    def test_italic(self):
        assert "<i>mundo</i>" in _markdown_to_telegram("*mundo*")

    def test_inline_code(self):
        assert "<code>git push</code>" in _markdown_to_telegram("`git push`")

    def test_code_block(self):
        md = "```python\nprint('hola')\n```"
        result = _markdown_to_telegram(md)
        assert "<pre><code>" in result
        assert "print('hola')" in result

    def test_code_block_no_lang(self):
        md = "```\nls -la\n```"
        result = _markdown_to_telegram(md)
        assert "<pre><code>ls -la</code></pre>" in result

    def test_header_h2(self):
        assert "<b>Titulo</b>" in _markdown_to_telegram("## Titulo")

    def test_header_h3(self):
        assert "<b>Sub</b>" in _markdown_to_telegram("### Sub")

    def test_bullet_list(self):
        result = _markdown_to_telegram("- item uno\n- item dos")
        assert "• item uno" in result
        assert "• item dos" in result

    def test_link(self):
        result = _markdown_to_telegram("[Google](https://google.com)")
        assert '<a href="https://google.com">Google</a>' in result

    def test_mixed_formatting(self):
        md = "## Hola\n\n**bold** y *italic* con `code`"
        result = _markdown_to_telegram(md)
        assert "<b>Hola</b>" in result
        assert "<b>bold</b>" in result
        assert "<code>code</code>" in result

    def test_code_block_preserved(self):
        """Code blocks no deben tener bold/italic dentro."""
        md = "```\n**no bold** *no italic*\n```"
        result = _markdown_to_telegram(md)
        assert "<b>" not in result.split("<pre>")[1]

    def test_plain_text_unchanged(self):
        result = _markdown_to_telegram("hola mundo")
        assert result == "hola mundo"

    def test_asterisk_in_math_not_italic(self):
        """Un * suelto no debe convertirse a italic."""
        result = _markdown_to_telegram("2 * 3 = 6")
        assert "<i>" not in result
