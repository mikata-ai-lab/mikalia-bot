"""
test_repo_analyzer.py — Tests para el analizador de repos.

Verifica que RepoAnalyzer pueda:
- Analizar repos locales correctamente
- Generar estructura de archivos
- Detectar lenguajes
- Identificar archivos clave
- Generar contexto formateado para prompts
"""

import os
import tempfile
from pathlib import Path

import pytest

from mikalia.generation.repo_analyzer import RepoAnalyzer, RepoContext


@pytest.fixture
def fake_repo(tmp_path):
    """Crea un repo falso con estructura de ejemplo."""
    # Crear archivos
    (tmp_path / "README.md").write_text(
        "# Test Project\n\nA test repository for unit tests.\n\n## Features\n- Feature 1"
    )
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='test')"
    )
    (tmp_path / "main.py").write_text(
        "def main():\n    print('hello')\n\nif __name__ == '__main__':\n    main()"
    )
    (tmp_path / "config.yaml").write_text(
        "name: test\nversion: 1.0"
    )

    # Crear subdirectorio
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "app.py").write_text(
        "class App:\n    def run(self):\n        pass"
    )
    (src / "utils.py").write_text(
        "def helper():\n    return True"
    )

    # Crear tests
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text(
        "def test_app():\n    assert True"
    )

    # Crear un .git fake para que parezca repo
    git_dir = tmp_path / ".git"
    git_dir.mkdir()

    return tmp_path


@pytest.fixture
def analyzer():
    """Crea un RepoAnalyzer con cache temporal."""
    with tempfile.TemporaryDirectory() as cache_dir:
        yield RepoAnalyzer(cache_dir=cache_dir)


class TestRepoAnalyzer:
    """Tests para la clase RepoAnalyzer."""

    def test_analyze_local_repo(self, analyzer, fake_repo):
        """Verifica que analiza un repo local correctamente."""
        ctx = analyzer.analyze(str(fake_repo))

        assert ctx.repo_name == fake_repo.name
        assert ctx.total_files > 0
        assert "test" in ctx.description.lower() or ctx.description != ""

    def test_readme_extraction(self, analyzer, fake_repo):
        """Verifica que extrae el README correctamente."""
        ctx = analyzer.analyze(str(fake_repo))

        assert "Test Project" in ctx.readme_content
        assert "Features" in ctx.readme_content

    def test_structure_analysis(self, analyzer, fake_repo):
        """Verifica que genera la estructura de archivos."""
        ctx = analyzer.analyze(str(fake_repo))

        assert ctx.structure != ""
        assert "src/" in ctx.structure or "main.py" in ctx.structure

    def test_language_detection(self, analyzer, fake_repo):
        """Verifica que detecta los lenguajes correctamente."""
        ctx = analyzer.analyze(str(fake_repo))

        assert "Python" in ctx.language_stats
        assert ctx.language_stats["Python"] >= 3  # main.py, app.py, utils.py, etc.

    def test_key_files_identification(self, analyzer, fake_repo):
        """Verifica que identifica archivos clave."""
        ctx = analyzer.analyze(str(fake_repo))

        # Debe encontrar README.md, setup.py, config.yaml
        assert len(ctx.key_files) > 0
        file_names = list(ctx.key_files.keys())
        assert any("README" in f for f in file_names)

    def test_focus_topic_finds_related_files(self, analyzer, fake_repo):
        """Verifica que el tema de enfoque encuentra archivos relacionados."""
        ctx = analyzer.analyze(str(fake_repo), focus_topic="app")

        # Debe encontrar app.py por el keyword
        file_names = list(ctx.key_files.keys())
        assert any("app" in f.lower() for f in file_names)

    def test_description_extraction(self, analyzer, fake_repo):
        """Verifica que extrae la descripción del README."""
        ctx = analyzer.analyze(str(fake_repo))

        # La descripción debe ser la primera línea no-heading
        assert "test repository" in ctx.description.lower()

    def test_nonexistent_repo_raises_error(self, analyzer):
        """Verifica que un repo local inexistente lanza error."""
        # Usar ruta absoluta de Windows para que no se confunda con owner/repo
        with pytest.raises(FileNotFoundError):
            analyzer.analyze(os.path.join("C:\\", "path_that_does_not_exist"))

    def test_invalid_format_raises_error(self, analyzer):
        """Verifica que un formato inválido lanza error."""
        with pytest.raises(ValueError):
            analyzer.analyze("not-a-repo-format")


class TestRepoContext:
    """Tests para la dataclass RepoContext."""

    def test_to_prompt_basic(self):
        """Verifica que to_prompt genera texto formateado."""
        ctx = RepoContext(
            repo_name="test/repo",
            description="A test repo",
            structure="repo/\n├── main.py\n└── README.md",
            readme_content="# Test\nThis is a test.",
            language_stats={"Python": 5, "YAML": 2},
            total_files=7,
        )

        prompt = ctx.to_prompt()
        assert "test/repo" in prompt
        assert "A test repo" in prompt
        assert "Python: 5 files" in prompt
        assert "main.py" in prompt

    def test_to_prompt_respects_max_tokens(self):
        """Verifica que to_prompt respeta el límite de tokens."""
        ctx = RepoContext(
            repo_name="test/repo",
            readme_content="x" * 50000,  # README muy largo
            key_files={"big.py": "y" * 50000},
        )

        prompt = ctx.to_prompt(max_tokens=1000)
        # El prompt debe estar truncado
        assert len(prompt) < 50000

    def test_to_prompt_empty_context(self):
        """Verifica que to_prompt funciona con contexto vacío."""
        ctx = RepoContext(repo_name="test/repo")
        prompt = ctx.to_prompt()
        assert "test/repo" in prompt
