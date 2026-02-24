"""
test_mcp_server.py — Tests para McpServerTool.

Verifica:
- Status del servidor MCP
- Exposicion y ocultacion de tools
- Bloqueo de tools peligrosos
- Manejo de requests MCP (initialize, tools/list, tools/call)
- Generacion de manifest
- Metadata del tool
"""

from __future__ import annotations

import json

import pytest
from unittest.mock import MagicMock

from mikalia.tools.mcp_server import McpServerTool, MCP_VERSION
from mikalia.tools.base import BaseTool, ToolResult


def _make_mock_registry():
    """Crea un mock registry con tools simulados."""
    mock_registry = MagicMock()
    mock_registry.list_tools.return_value = ["weather", "file_read", "shell_exec"]
    mock_registry.get.return_value = MagicMock(
        to_claude_definition=MagicMock(
            return_value={
                "name": "weather",
                "description": "Get weather",
                "input_schema": {"type": "object", "properties": {}},
            }
        )
    )
    mock_registry.execute.return_value = ToolResult(
        success=True, output="sunny 25C"
    )
    return mock_registry


# ================================================================
# Status
# ================================================================

class TestMcpStatus:
    def test_status(self):
        """Status muestra info del servidor y tools."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        result = tool.execute(action="status")
        assert result.success
        assert "MCP Server" in result.output
        assert "mikalia-mcp" in result.output
        assert "Tools disponibles: 3" in result.output
        assert "Tools expuestos: 0" in result.output


# ================================================================
# Expose / hide
# ================================================================

class TestMcpExpose:
    def test_expose_tool(self):
        """Exponer un tool valido lo agrega a la lista."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        result = tool.execute(action="expose", tool_name="weather")
        assert result.success
        assert "weather" in result.output
        assert "expuesto" in result.output

        # Verificar que aparece en status
        status = tool.execute(action="status")
        assert "Tools expuestos: 1" in status.output
        assert "weather" in status.output

    def test_expose_dangerous_tool_blocked(self):
        """Tools peligrosos no se pueden exponer."""
        mock_registry = _make_mock_registry()
        mock_registry.list_tools.return_value = [
            "weather", "file_read", "shell_exec", "file_write", "git_push"
        ]

        tool = McpServerTool(registry=mock_registry)

        for dangerous_name in ["shell_exec", "file_write", "git_push"]:
            result = tool.execute(action="expose", tool_name=dangerous_name)
            assert not result.success
            assert "peligroso" in result.error

    def test_hide_tool(self):
        """Ocultar un tool expuesto lo remueve."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        # Exponer y luego ocultar
        tool.execute(action="expose", tool_name="weather")
        result = tool.execute(action="hide", tool_name="weather")
        assert result.success
        assert "removido" in result.output

        # Verificar que ya no esta expuesto
        status = tool.execute(action="status")
        assert "Tools expuestos: 0" in status.output

    def test_hide_unexposed_tool_fails(self):
        """Ocultar un tool no expuesto falla."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        result = tool.execute(action="hide", tool_name="weather")
        assert not result.success
        assert "no esta expuesto" in result.error


# ================================================================
# Handle MCP requests
# ================================================================

class TestMcpHandle:
    def test_handle_initialize_request(self):
        """Initialize request retorna info del servidor."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        })

        result = tool.execute(action="handle", request=request)
        assert result.success

        response = json.loads(result.output)
        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 1
        assert "result" in response
        assert response["result"]["protocolVersion"] == MCP_VERSION
        assert "serverInfo" in response["result"]
        assert "capabilities" in response["result"]

    def test_handle_tools_list(self):
        """tools/list retorna los tools expuestos."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        # Exponer un tool primero
        tool.execute(action="expose", tool_name="weather")

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        })

        result = tool.execute(action="handle", request=request)
        assert result.success

        response = json.loads(result.output)
        assert response["id"] == 2
        tools_list = response["result"]["tools"]
        assert len(tools_list) == 1
        assert tools_list[0]["name"] == "weather"
        assert "inputSchema" in tools_list[0]

    def test_handle_tool_call(self):
        """tools/call ejecuta el tool y retorna resultado."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        # Exponer weather
        tool.execute(action="expose", tool_name="weather")

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "weather",
                "arguments": {"city": "Monterrey"},
            },
        })

        result = tool.execute(action="handle", request=request)
        assert result.success

        response = json.loads(result.output)
        assert response["id"] == 3
        assert "result" in response
        content = response["result"]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert "sunny" in content[0]["text"]
        assert response["result"]["isError"] is False

        # Verificar que registry.execute fue llamado
        mock_registry.execute.assert_called_once_with(
            "weather", {"city": "Monterrey"}
        )

    def test_handle_tool_call_unexposed_fails(self):
        """Llamar un tool no expuesto falla."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        request = json.dumps({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "weather", "arguments": {}},
        })

        result = tool.execute(action="handle", request=request)
        assert not result.success
        error_data = json.loads(result.error)
        assert "not available" in error_data["error"]["message"]

    def test_handle_invalid_json(self):
        """JSON invalido retorna parse error."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        result = tool.execute(action="handle", request="not json{{{")
        assert not result.success
        error_data = json.loads(result.error)
        assert error_data["error"]["code"] == -32700


# ================================================================
# Manifest
# ================================================================

class TestMcpManifest:
    def test_manifest(self):
        """Manifest genera JSON con server info y tools expuestos."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        # Exponer un tool
        tool.execute(action="expose", tool_name="weather")

        result = tool.execute(action="manifest")
        assert result.success

        manifest = json.loads(result.output)
        assert "server" in manifest
        assert manifest["server"]["name"] == "mikalia-mcp"
        assert "tools" in manifest
        assert len(manifest["tools"]) == 1
        assert manifest["tools"][0]["name"] == "weather"

    def test_manifest_empty(self):
        """Manifest sin tools expuestos retorna lista vacia."""
        mock_registry = _make_mock_registry()
        tool = McpServerTool(registry=mock_registry)

        result = tool.execute(action="manifest")
        assert result.success

        manifest = json.loads(result.output)
        assert manifest["tools"] == []


# ================================================================
# Metadata
# ================================================================

class TestMcpMetadata:
    def test_tool_metadata(self):
        """Metadata del tool es correcta."""
        tool = McpServerTool()
        assert tool.name == "mcp_server"
        assert "MCP" in tool.description

        defn = tool.to_claude_definition()
        assert defn["name"] == "mcp_server"
        assert "input_schema" in defn
        assert "action" in defn["input_schema"]["properties"]
        assert "tool_name" in defn["input_schema"]["properties"]
        assert "request" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["properties"]["action"]["enum"] == [
            "status", "expose", "hide", "handle", "manifest"
        ]
