"""
test_doc_analyzer.py — Tests para el analizador de documentos.

Verifica que DocAnalyzer pueda:
- Leer archivos markdown/txt correctamente
- Leer archivos YAML/JSON correctamente
- Extraer secciones de documentos
- Generar contexto formateado para prompts
- Manejar errores graciosamente
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from mikalia.generation.doc_analyzer import DocAnalyzer, DocContext


@pytest.fixture
def analyzer():
    """Crea un DocAnalyzer."""
    return DocAnalyzer()


@pytest.fixture
def md_file(tmp_path):
    """Crea un archivo markdown de ejemplo."""
    contenido = """# Architecture Document

## Overview
This document describes the architecture of Mikalia Bot.

## Components
- **CLI**: Click-based command interface
- **Generator**: Post generation with Claude API
- **Publisher**: Hugo formatting and Git operations

## Design Decisions
We chose Python because of the Anthropic SDK.

## Conclusion
The architecture is modular and extensible.
"""
    ruta = tmp_path / "architecture.md"
    ruta.write_text(contenido)
    return ruta


@pytest.fixture
def yaml_file(tmp_path):
    """Crea un archivo YAML de ejemplo."""
    datos = {
        "name": "mikalia-bot",
        "version": "1.0.0",
        "components": {
            "cli": {"framework": "click"},
            "generation": {"model": "claude-sonnet"},
            "publishing": {"target": "hugo"},
        },
    }
    ruta = tmp_path / "config.yaml"
    ruta.write_text(yaml.dump(datos))
    return ruta


@pytest.fixture
def json_file(tmp_path):
    """Crea un archivo JSON de ejemplo."""
    datos = {
        "name": "test-project",
        "dependencies": {"anthropic": "0.42.0", "rich": "13.0.0"},
        "scripts": {"test": "pytest", "lint": "ruff check ."},
    }
    ruta = tmp_path / "package.json"
    ruta.write_text(json.dumps(datos, indent=2))
    return ruta


@pytest.fixture
def txt_file(tmp_path):
    """Crea un archivo de texto plano."""
    ruta = tmp_path / "notes.txt"
    ruta.write_text("These are some notes about the project.\nLine 2.\nLine 3.")
    return ruta


class TestDocAnalyzer:
    """Tests para la clase DocAnalyzer."""

    def test_analyze_markdown(self, analyzer, md_file):
        """Verifica que lee archivos markdown correctamente."""
        ctx = analyzer.analyze(str(md_file))

        assert ctx.doc_name == "architecture.md"
        assert ctx.doc_format == "markdown"
        assert "Architecture Document" in ctx.content
        assert ctx.total_chars > 0

    def test_markdown_sections_extracted(self, analyzer, md_file):
        """Verifica que extrae secciones de markdown."""
        ctx = analyzer.analyze(str(md_file))

        assert len(ctx.key_sections) > 0
        section_names = ctx.key_sections
        assert "Overview" in section_names
        assert "Components" in section_names

    def test_analyze_yaml(self, analyzer, yaml_file):
        """Verifica que lee archivos YAML correctamente."""
        ctx = analyzer.analyze(str(yaml_file))

        assert ctx.doc_format == "yaml"
        assert "mikalia-bot" in ctx.content
        assert len(ctx.key_sections) > 0

    def test_yaml_keys_as_sections(self, analyzer, yaml_file):
        """Verifica que las keys YAML se detectan como secciones."""
        ctx = analyzer.analyze(str(yaml_file))

        assert "name" in ctx.key_sections
        assert "components" in ctx.key_sections

    def test_analyze_json(self, analyzer, json_file):
        """Verifica que lee archivos JSON correctamente."""
        ctx = analyzer.analyze(str(json_file))

        assert ctx.doc_format == "json"
        assert "test-project" in ctx.content
        assert "dependencies" in ctx.key_sections

    def test_analyze_txt(self, analyzer, txt_file):
        """Verifica que lee archivos de texto plano."""
        ctx = analyzer.analyze(str(txt_file))

        assert ctx.doc_format == "text"
        assert "notes about the project" in ctx.content

    def test_nonexistent_file_raises_error(self, analyzer):
        """Verifica que un archivo inexistente lanza error."""
        with pytest.raises(FileNotFoundError):
            analyzer.analyze("/path/that/does/not/exist.md")

    def test_unsupported_format_raises_error(self, analyzer, tmp_path):
        """Verifica que un formato no soportado lanza error."""
        ruta = tmp_path / "file.xyz"
        ruta.write_text("content")
        with pytest.raises(ValueError):
            analyzer.analyze(str(ruta))

    def test_summary_generated(self, analyzer, md_file):
        """Verifica que se genera un resumen."""
        ctx = analyzer.analyze(str(md_file))

        assert ctx.summary != ""
        assert len(ctx.summary) <= 500


class TestDocContext:
    """Tests para la dataclass DocContext."""

    def test_to_prompt_basic(self):
        """Verifica que to_prompt genera texto formateado."""
        ctx = DocContext(
            doc_name="test.md",
            doc_format="markdown",
            content="# Test\nSome content here.",
            summary="Some content here.",
            key_sections=["Test"],
            total_chars=25,
        )

        prompt = ctx.to_prompt()
        assert "test.md" in prompt
        assert "markdown" in prompt
        assert "Test" in prompt

    def test_to_prompt_truncates_long_content(self):
        """Verifica que to_prompt trunca contenido largo."""
        ctx = DocContext(
            doc_name="big.md",
            doc_format="markdown",
            content="x" * 100000,
            total_chars=100000,
        )

        prompt = ctx.to_prompt(max_tokens=500)
        assert "truncated" in prompt.lower()
        assert len(prompt) < 100000

    def test_to_prompt_empty(self):
        """Verifica que to_prompt funciona con contexto vacío."""
        ctx = DocContext(doc_name="empty.md")
        prompt = ctx.to_prompt()
        assert "empty.md" in prompt
