"""
test_skill_creator.py — Tests para el sistema de auto-skills.

Verifica:
- Validacion de seguridad (patrones peligrosos, imports)
- Creacion de skills validos
- Rechazo de skills invalidos
- Import dinamico y registro en ToolRegistry
- Carga de skills custom existentes
- ListSkillsTool
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from mikalia.core.memory import MemoryManager
from mikalia.core.skill_creator import SkillCreator
from mikalia.tools.registry import ToolRegistry


SCHEMA_PATH = Path(__file__).parent.parent / "mikalia" / "core" / "schema.sql"

# Codigo de un skill valido para tests
VALID_SKILL_CODE = '''
from __future__ import annotations
from typing import Any
from mikalia.tools.base import BaseTool, ToolResult

class TimestampTool(BaseTool):
    """Retorna el timestamp actual."""

    @property
    def name(self) -> str:
        return "timestamp"

    @property
    def description(self) -> str:
        return "Get current timestamp"

    def get_parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, **_: Any) -> ToolResult:
        import datetime
        now = datetime.datetime.now().isoformat()
        return ToolResult(success=True, output=f"Timestamp: {now}")
'''

# Codigo con patron peligroso
DANGEROUS_CODE_EVAL = '''
from mikalia.tools.base import BaseTool, ToolResult

class EvilTool(BaseTool):
    @property
    def name(self): return "evil"
    @property
    def description(self): return "evil"
    def get_parameters(self): return {"type": "object", "properties": {}}
    def execute(self, **_):
        result = eval("2 + 2")
        return ToolResult(success=True, output=str(result))
'''

# Codigo con import no permitido
BAD_IMPORT_CODE = '''
import subprocess
from mikalia.tools.base import BaseTool, ToolResult

class BadTool(BaseTool):
    @property
    def name(self): return "bad"
    @property
    def description(self): return "bad"
    def get_parameters(self): return {"type": "object", "properties": {}}
    def execute(self, **_):
        return ToolResult(success=True, output="bad")
'''


@pytest.fixture
def memory(tmp_path):
    db_path = tmp_path / "test.db"
    return MemoryManager(str(db_path), str(SCHEMA_PATH))


@pytest.fixture
def registry(memory):
    return ToolRegistry.with_defaults(memory=memory)


@pytest.fixture
def creator(memory, registry, tmp_path):
    c = SkillCreator(memory, registry)
    # Usar directorio temporal para custom tools
    import mikalia.core.skill_creator as sc
    sc.CUSTOM_TOOLS_DIR = tmp_path / "custom_tools"
    sc.CUSTOM_TOOLS_DIR.mkdir()
    (sc.CUSTOM_TOOLS_DIR / "__init__.py").write_text("")
    return c


# ================================================================
# Validacion de seguridad
# ================================================================

class TestSafety:
    def test_valid_code_passes(self, creator):
        """Codigo seguro pasa validacion."""
        result = creator._validate_safety(VALID_SKILL_CODE)
        assert result["safe"] is True

    def test_eval_rejected(self, creator):
        """Codigo con eval() es rechazado."""
        result = creator._validate_safety(DANGEROUS_CODE_EVAL)
        assert result["safe"] is False
        assert "peligroso" in result["reason"].lower() or "Patron" in result["reason"]

    def test_bad_import_rejected(self, creator):
        """Codigo con import no permitido es rechazado."""
        result = creator._validate_safety(BAD_IMPORT_CODE)
        assert result["safe"] is False
        assert "import" in result["reason"].lower()

    def test_os_system_rejected(self, creator):
        """os.system es rechazado."""
        code = 'import os\nos.system("rm -rf /")'
        result = creator._validate_safety(code)
        assert result["safe"] is False

    def test_mikalia_imports_allowed(self, creator):
        """Imports de mikalia.* son permitidos."""
        code = '''
from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger
'''
        result = creator._validate_safety(code)
        assert result["safe"] is True


# ================================================================
# Creacion de skills
# ================================================================

class TestCreateSkill:
    def test_create_valid_skill(self, creator):
        """Crea un skill valido exitosamente."""
        result = creator.create_skill(
            name="timestamp_tool",
            description="Get current timestamp",
            code=VALID_SKILL_CODE,
        )
        assert result.success
        assert "timestamp_tool" in result.output

    def test_invalid_name_rejected(self, creator):
        """Nombre invalido es rechazado."""
        result = creator.create_skill(
            name="Bad-Name!",
            description="test",
            code=VALID_SKILL_CODE,
        )
        assert not result.success
        assert "invalido" in result.error.lower()

    def test_short_name_rejected(self, creator):
        """Nombre muy corto es rechazado."""
        result = creator.create_skill(
            name="ab",
            description="test",
            code=VALID_SKILL_CODE,
        )
        assert not result.success

    def test_dangerous_code_rejected(self, creator):
        """Codigo peligroso es rechazado."""
        result = creator.create_skill(
            name="evil_tool",
            description="evil",
            code=DANGEROUS_CODE_EVAL,
        )
        assert not result.success
        assert "seguridad" in result.error.lower()

    def test_no_basetool_rejected(self, creator):
        """Codigo sin BaseTool es rechazado."""
        code = '''
def hello():
    return "hello"
'''
        result = creator.create_skill(
            name="no_base",
            description="test",
            code=code,
        )
        assert not result.success
        assert "BaseTool" in result.error

    def test_created_skill_is_registered(self, creator, registry):
        """Skill creado se registra en el ToolRegistry."""
        creator.create_skill(
            name="timestamp_tool",
            description="Get timestamp",
            code=VALID_SKILL_CODE,
        )
        assert registry.get("timestamp") is not None

    def test_created_skill_is_executable(self, creator, registry):
        """Skill creado se puede ejecutar."""
        creator.create_skill(
            name="timestamp_tool",
            description="Get timestamp",
            code=VALID_SKILL_CODE,
        )
        result = registry.execute("timestamp", {})
        assert result.success
        assert "Timestamp:" in result.output


# ================================================================
# Carga de skills existentes
# ================================================================

class TestLoadSkills:
    def test_load_from_empty_dir(self, creator):
        """Cargar de directorio vacio retorna 0."""
        count = creator.load_custom_skills()
        assert count == 0

    def test_load_persisted_skill(self, creator, registry):
        """Skills guardados se cargan al reiniciar."""
        # Crear skill
        creator.create_skill(
            name="timestamp_tool",
            description="Get timestamp",
            code=VALID_SKILL_CODE,
        )

        # Crear nuevo registry (simula reinicio)
        new_registry = ToolRegistry()
        new_creator = SkillCreator(creator._memory, new_registry)

        import mikalia.core.skill_creator as sc
        new_creator.load_custom_skills()

        # El skill debe estar en el nuevo registry
        assert new_registry.get("timestamp") is not None


# ================================================================
# ListSkillsTool
# ================================================================

class TestListSkillsTool:
    def test_list_empty(self, creator):
        """list_custom_skills retorna lista vacia."""
        skills = creator.list_custom_skills()
        assert skills == []

    def test_list_after_create(self, creator):
        """list_custom_skills muestra skill creado."""
        creator.create_skill(
            name="timestamp_tool",
            description="Get timestamp",
            code=VALID_SKILL_CODE,
        )
        skills = creator.list_custom_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "timestamp_tool"
