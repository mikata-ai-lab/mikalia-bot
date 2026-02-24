"""
test_system_monitor.py — Tests para SystemMonitorTool.

Verifica:
- Output incluye info del OS
- Output incluye version de Python
- Output incluye uptime
- Disk info presente/ausente segun parametro
- Definicion Claude correcta
"""

from __future__ import annotations

import platform
import pytest
from unittest.mock import patch

from mikalia.tools.system_monitor import SystemMonitorTool


# ================================================================
# SystemMonitorTool
# ================================================================

class TestSystemMonitorTool:

    def test_basic_output_has_os_info(self):
        """Output contiene informacion del sistema operativo."""
        tool = SystemMonitorTool()
        result = tool.execute()

        assert result.success
        assert "System Info" in result.output
        assert "OS:" in result.output
        assert platform.system() in result.output

    def test_includes_python_version(self):
        """Output incluye la version de Python."""
        tool = SystemMonitorTool()
        result = tool.execute()

        assert result.success
        assert "Python:" in result.output
        assert platform.python_version() in result.output

    def test_includes_uptime(self):
        """Output incluye el uptime del proceso."""
        tool = SystemMonitorTool()
        result = tool.execute()

        assert result.success
        assert "uptime:" in result.output.lower()

    def test_includes_disk_when_enabled(self):
        """Cuando include_disk=True, la seccion Disk aparece."""
        tool = SystemMonitorTool()
        result = tool.execute(include_disk=True)

        assert result.success
        # Disk section deberia existir (usa shutil.disk_usage)
        assert "Disk" in result.output or "disk" in result.output.lower()

    def test_no_disk_when_disabled(self):
        """Cuando include_disk=False, la seccion Disk no aparece."""
        tool = SystemMonitorTool()
        result = tool.execute(include_disk=False)

        assert result.success
        assert "=== Disk ===" not in result.output

    def test_tool_metadata(self):
        """Tool tiene nombre, descripcion y parametros correctos."""
        tool = SystemMonitorTool()

        assert tool.name == "system_monitor"
        assert "monitor" in tool.description.lower() or "system" in tool.description.lower()

        params = tool.get_parameters()
        assert params["type"] == "object"
        assert "include_disk" in params["properties"]
        assert params["required"] == []

        defn = tool.to_claude_definition()
        assert defn["name"] == "system_monitor"
        assert "input_schema" in defn
        assert "description" in defn
