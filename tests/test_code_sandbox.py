"""
test_code_sandbox.py — Tests para CodeSandboxTool.

Verifica:
- Ejecucion simple (mock subprocess.run)
- Codigo vacio
- Import bloqueado
- Patron peligroso bloqueado
- Timeout
- Error de ejecucion (exit code != 0)
- Timeout maximo se limita a MAX_TIMEOUT
- Definicion Claude correcta
"""

from __future__ import annotations

import subprocess
import pytest
from unittest.mock import patch, MagicMock

from mikalia.tools.code_sandbox import CodeSandboxTool, MAX_TIMEOUT, BLOCKED_IMPORTS, BLOCKED_PATTERNS


# ================================================================
# CodeSandboxTool
# ================================================================

class TestCodeSandboxTool:

    @patch("mikalia.tools.code_sandbox.Path")
    @patch("mikalia.tools.code_sandbox.subprocess.run")
    @patch("mikalia.tools.code_sandbox.tempfile.NamedTemporaryFile")
    def test_execute_simple_code(self, mock_tempfile, mock_run, mock_path):
        """Codigo simple se ejecuta y retorna output."""
        # Mock del archivo temporal
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.name = "/tmp/test_code.py"
        mock_tempfile.return_value = mock_file

        # Mock de Path.unlink
        mock_path_inst = MagicMock()
        mock_path.return_value = mock_path_inst

        # Mock de subprocess.run
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Hello World\n"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        tool = CodeSandboxTool()
        result = tool.execute(code='print("Hello World")')

        assert result.success
        assert "Hello World" in result.output
        mock_run.assert_called_once()

    def test_empty_code_error(self):
        """Codigo vacio retorna error."""
        tool = CodeSandboxTool()
        result = tool.execute(code="   ")

        assert not result.success
        assert "vacio" in result.error.lower()

    def test_blocked_import_rejected(self):
        """Import de modulo peligroso (subprocess) es rechazado."""
        tool = CodeSandboxTool()
        result = tool.execute(code="import subprocess\nsubprocess.run(['ls'])")

        assert not result.success
        assert "bloqueado" in result.error.lower() or "blocked" in result.error.lower()

    def test_blocked_pattern_rejected(self):
        """Patron peligroso (eval() es rechazado."""
        tool = CodeSandboxTool()
        result = tool.execute(code='result = eval("2 + 2")\nprint(result)')

        assert not result.success
        assert "bloqueado" in result.error.lower() or "blocked" in result.error.lower()

    @patch("mikalia.tools.code_sandbox.Path")
    @patch("mikalia.tools.code_sandbox.subprocess.run")
    @patch("mikalia.tools.code_sandbox.tempfile.NamedTemporaryFile")
    def test_timeout_error(self, mock_tempfile, mock_run, mock_path):
        """TimeoutExpired retorna error de timeout."""
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.name = "/tmp/test_timeout.py"
        mock_tempfile.return_value = mock_file

        mock_path_inst = MagicMock()
        mock_path.return_value = mock_path_inst

        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["python", "/tmp/test_timeout.py"], timeout=10
        )

        tool = CodeSandboxTool()
        result = tool.execute(code="import time\ntime.sleep(100)")

        assert not result.success
        assert "timeout" in result.error.lower()

    @patch("mikalia.tools.code_sandbox.Path")
    @patch("mikalia.tools.code_sandbox.subprocess.run")
    @patch("mikalia.tools.code_sandbox.tempfile.NamedTemporaryFile")
    def test_execution_error(self, mock_tempfile, mock_run, mock_path):
        """Exit code != 0 retorna error con stderr."""
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.name = "/tmp/test_error.py"
        mock_tempfile.return_value = mock_file

        mock_path_inst = MagicMock()
        mock_path.return_value = mock_path_inst

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "NameError: name 'x' is not defined"
        mock_run.return_value = mock_result

        tool = CodeSandboxTool()
        result = tool.execute(code="print(x)")

        assert not result.success
        assert "Exit code 1" in result.error
        assert "NameError" in result.error

    def test_max_timeout_clamped(self):
        """Timeout mayor a MAX_TIMEOUT se limita automaticamente."""
        tool = CodeSandboxTool()

        # Usamos _check_safety para confirmar que el code pasa seguridad,
        # luego verificamos que el timeout se clampea en execute
        with patch("mikalia.tools.code_sandbox.Path") as mock_path, \
             patch("mikalia.tools.code_sandbox.subprocess.run") as mock_run, \
             patch("mikalia.tools.code_sandbox.tempfile.NamedTemporaryFile") as mock_tempfile:

            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_file.name = "/tmp/test_clamp.py"
            mock_tempfile.return_value = mock_file

            mock_path_inst = MagicMock()
            mock_path.return_value = mock_path_inst

            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "ok"
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            tool.execute(code="print('ok')", timeout=999)

            # Verificar que subprocess.run fue llamado con timeout <= MAX_TIMEOUT
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] <= MAX_TIMEOUT

    def test_tool_metadata(self):
        """Tool tiene nombre, descripcion y parametros correctos."""
        tool = CodeSandboxTool()

        assert tool.name == "code_sandbox"
        assert "python" in tool.description.lower() or "sandbox" in tool.description.lower()

        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "code" in params["properties"]
        assert "timeout" in params["properties"]
        assert "code" in params["required"]

        defn = tool.to_claude_definition()
        assert defn["name"] == "code_sandbox"
        assert "input_schema" in defn
        assert "description" in defn
