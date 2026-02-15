"""
test_config.py — Tests para el módulo de configuración.

Verificamos que:
1. La configuración se carga correctamente desde config.yaml
2. Las variables de entorno se resuelven
3. Los valores por defecto funcionan cuando no hay archivo
4. Las dataclasses se crean con los tipos correctos
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from mikalia.config import (
    AppConfig,
    MikaliaConfig,
    BlogConfig,
    load_config,
    _resolve_env_vars,
    _resolve_env_recursive,
)


class TestResolveEnvVars:
    """Tests para la resolución de variables de entorno."""

    def test_resuelve_variable_existente(self):
        """Debe reemplazar ${VAR} con el valor de la variable de entorno."""
        with patch.dict("os.environ", {"MI_VAR": "hola"}):
            resultado = _resolve_env_vars("${MI_VAR}/path")
            assert resultado == "hola/path"

    def test_mantiene_variable_inexistente(self):
        """Si la variable no existe, debe mantener el placeholder."""
        resultado = _resolve_env_vars("${NO_EXISTE}")
        assert resultado == "${NO_EXISTE}"

    def test_resuelve_multiples_variables(self):
        """Debe resolver múltiples variables en un solo string."""
        with patch.dict("os.environ", {"A": "1", "B": "2"}):
            resultado = _resolve_env_vars("${A}-${B}")
            assert resultado == "1-2"

    def test_string_sin_variables(self):
        """Strings sin ${} deben quedarse igual."""
        resultado = _resolve_env_vars("sin variables")
        assert resultado == "sin variables"


class TestResolveEnvRecursive:
    """Tests para la resolución recursiva en estructuras de datos."""

    def test_resuelve_en_dict_anidado(self):
        """Debe resolver variables dentro de dicts anidados."""
        with patch.dict("os.environ", {"PATH_VAR": "/mi/path"}):
            datos = {"nivel1": {"nivel2": "${PATH_VAR}"}}
            resultado = _resolve_env_recursive(datos)
            assert resultado["nivel1"]["nivel2"] == "/mi/path"

    def test_resuelve_en_lista(self):
        """Debe resolver variables dentro de listas."""
        with patch.dict("os.environ", {"VAL": "ok"}):
            datos = ["${VAL}", "fijo"]
            resultado = _resolve_env_recursive(datos)
            assert resultado == ["ok", "fijo"]

    def test_no_modifica_numeros(self):
        """Los valores numéricos deben pasar sin cambios."""
        resultado = _resolve_env_recursive(42)
        assert resultado == 42


class TestAppConfig:
    """Tests para la configuración completa de la app."""

    def test_valores_por_defecto(self):
        """AppConfig debe tener valores por defecto sensatos."""
        config = AppConfig()
        assert config.mikalia.model == "claude-sonnet-4-5-20250929"
        assert config.mikalia.max_tokens == 4096
        assert config.mikalia.generation_temperature == 0.7
        assert config.mikalia.review_temperature == 0.3
        assert config.blog.author == "Mikalia"
        assert config.blog.timezone == "America/Monterrey"
        assert config.git.default_branch == "main"

    def test_blog_config_page_bundles(self):
        """BlogConfig debe usar page bundles de Blowfish."""
        config = BlogConfig()
        assert config.content_base == "content/blog"
        assert config.en_filename == "index.md"
        assert config.es_filename == "index.es.md"


class TestLoadConfig:
    """Tests para la función load_config."""

    def test_carga_sin_archivo(self, tmp_path):
        """Si no hay config.yaml, debe usar valores por defecto."""
        # Cambiar directorio de trabajo a uno sin config.yaml
        with patch("mikalia.config._find_config_dir", return_value=tmp_path):
            config = load_config()
            assert isinstance(config, AppConfig)
            assert config.mikalia.model == "claude-sonnet-4-5-20250929"
