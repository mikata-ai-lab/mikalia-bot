"""
test_safety.py — Tests para el guardián de seguridad.

ESTE ES EL TEST MÁS IMPORTANTE DEL PROYECTO.
Si safety.py falla, Mikalia podría hacer daño.

Verifica que:
- Archivos de secrets SIEMPRE están bloqueados
- Branches protegidos SIEMPRE están bloqueados
- Extensiones no permitidas están bloqueadas
- Límites de tamaño se respetan
- Patrones peligrosos se detectan
"""

import pytest

from mikalia.agent.safety import SafetyGuard, SafetyConfig, SafetyResult, Severity


@pytest.fixture
def guard():
    """SafetyGuard con configuración por defecto."""
    return SafetyGuard()


@pytest.fixture
def strict_guard():
    """SafetyGuard con límites estrictos."""
    config = SafetyConfig(
        max_files_per_pr=3,
        max_lines_changed=100,
    )
    return SafetyGuard(config)


class TestFileAccess:
    """Tests para verificación de acceso a archivos."""

    def test_env_file_always_blocked(self, guard):
        """REGLA ABSOLUTA: .env siempre bloqueado."""
        result = guard.check_file_access(".env")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_pem_file_always_blocked(self, guard):
        """REGLA ABSOLUTA: *.pem siempre bloqueado."""
        result = guard.check_file_access("mikalia-app.pem")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_key_file_blocked(self, guard):
        """REGLA ABSOLUTA: *.key siempre bloqueado."""
        result = guard.check_file_access("secrets/api.key")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_secrets_dir_blocked(self, guard):
        """REGLA ABSOLUTA: secrets/ siempre bloqueado."""
        result = guard.check_file_access("secrets/config.yaml")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_workflow_files_blocked(self, guard):
        """REGLA ABSOLUTA: .github/workflows/ siempre bloqueado."""
        result = guard.check_file_access(".github/workflows/test.yml")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_python_file_allowed(self, guard):
        """Archivos .py deben estar permitidos."""
        result = guard.check_file_access("mikalia/cli.py")
        assert result.allowed
        assert result.severity == Severity.OK

    def test_markdown_file_allowed(self, guard):
        """Archivos .md deben estar permitidos."""
        result = guard.check_file_access("README.md")
        assert result.allowed

    def test_yaml_file_allowed(self, guard):
        """Archivos .yaml deben estar permitidos."""
        result = guard.check_file_access("config.yaml")
        assert result.allowed

    def test_unknown_extension_blocked(self, guard):
        """Extensiones desconocidas deben estar bloqueadas."""
        result = guard.check_file_access("data.exe")
        assert not result.allowed
        assert result.severity == Severity.BLOCKED

    def test_env_in_subdirectory_blocked(self, guard):
        """Un .env dentro de un subdirectorio también está bloqueado."""
        result = guard.check_file_access("subdir/.env")
        assert not result.allowed


class TestBranchProtection:
    """Tests para protección de branches."""

    def test_main_always_protected(self, guard):
        """REGLA ABSOLUTA: main siempre protegido."""
        result = guard.check_branch_push("main")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_master_always_protected(self, guard):
        """REGLA ABSOLUTA: master siempre protegido."""
        result = guard.check_branch_push("master")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_production_protected(self, guard):
        """Production branch protegido."""
        result = guard.check_branch_push("production")
        assert not result.allowed

    def test_mikalia_branch_allowed(self, guard):
        """Branches de Mikalia deben estar permitidos."""
        result = guard.check_branch_push("mikalia/feat/add-validation")
        assert result.allowed
        assert result.severity == Severity.OK

    def test_non_convention_branch_warning(self, guard):
        """Branches que no siguen convención dan warning."""
        result = guard.check_branch_push("feature/random-branch")
        assert result.allowed
        assert result.severity == Severity.WARNING


class TestChangeSize:
    """Tests para límites de tamaño de cambios."""

    def test_small_changes_allowed(self, guard):
        """Cambios pequeños deben estar permitidos."""
        result = guard.check_change_size(2, 50)
        assert result.allowed
        assert result.severity == Severity.OK

    def test_too_many_files_blocked(self, strict_guard):
        """Demasiados archivos deben estar bloqueados."""
        result = strict_guard.check_change_size(5, 50)
        assert not result.allowed
        assert result.severity == Severity.BLOCKED

    def test_too_many_lines_blocked(self, strict_guard):
        """Demasiadas líneas deben estar bloqueadas."""
        result = strict_guard.check_change_size(1, 200)
        assert not result.allowed
        assert result.severity == Severity.BLOCKED

    def test_near_limit_gives_warning(self, strict_guard):
        """Cambios cerca del límite dan warning."""
        result = strict_guard.check_change_size(3, 50)
        assert result.allowed
        assert result.severity == Severity.WARNING


class TestContentSafety:
    """Tests para verificación de contenido."""

    def test_rm_rf_detected(self, guard):
        """Patrón rm -rf debe ser detectado."""
        result = guard.check_content_safety("os.system('rm -rf /')")
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_drop_table_detected(self, guard):
        """Patrón DROP TABLE debe ser detectado."""
        result = guard.check_content_safety("cursor.execute('DROP TABLE users')")
        assert not result.allowed

    def test_eval_detected(self, guard):
        """Patrón eval() debe ser detectado."""
        result = guard.check_content_safety("result = eval(user_input)")
        assert not result.allowed

    def test_normal_code_safe(self, guard):
        """Código normal debe pasar."""
        result = guard.check_content_safety(
            "def hello():\n    print('Hello world')\n    return True"
        )
        assert result.allowed


class TestValidateTask:
    """Tests para validación completa de tareas."""

    def test_valid_task_passes(self, guard):
        """Una tarea válida debe pasar todas las verificaciones."""
        result = guard.validate_task(
            files_to_modify=["mikalia/cli.py", "tests/test_cli.py"],
            target_branch="mikalia/feat/add-feature",
            total_lines=50,
        )
        assert result.allowed

    def test_task_with_env_file_blocked(self, guard):
        """Tarea que toca .env debe ser bloqueada."""
        result = guard.validate_task(
            files_to_modify=["mikalia/cli.py", ".env"],
            target_branch="mikalia/feat/add-feature",
        )
        assert not result.allowed
        assert result.severity == Severity.CRITICAL

    def test_task_to_main_blocked(self, guard):
        """Tarea que pushea a main debe ser bloqueada."""
        result = guard.validate_task(
            files_to_modify=["mikalia/cli.py"],
            target_branch="main",
        )
        assert not result.allowed

    def test_helper_methods(self, guard):
        """Atajos de conveniencia funcionan."""
        assert guard.is_blocked_path(".env")
        assert not guard.is_blocked_path("mikalia/cli.py")
        assert guard.is_allowed_extension("file.py")
        assert not guard.is_allowed_extension("file.exe")
        assert guard.is_protected_branch("main")
        assert not guard.is_protected_branch("mikalia/feat/test")
