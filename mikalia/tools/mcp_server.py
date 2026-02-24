"""
mcp_server.py — Model Context Protocol server para Mikalia.

Expone las herramientas de Mikalia como un servidor MCP,
permitiendo que otros AI agents las usen.

MCP es un protocolo estandar para que AI models
accedan a herramientas y datos contextuales.
"""

from __future__ import annotations

import json
from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.mcp_server")

MCP_VERSION = "2024-11-05"


class McpServerTool(BaseTool):
    """Gestiona un servidor MCP que expone herramientas de Mikalia."""

    def __init__(self, registry=None) -> None:
        self._registry = registry
        self._exposed_tools: list[str] = []
        self._server_info = {
            "name": "mikalia-mcp",
            "version": "1.0.0",
            "protocol_version": MCP_VERSION,
        }

    @property
    def name(self) -> str:
        return "mcp_server"

    @property
    def description(self) -> str:
        return (
            "Manage Mikalia's MCP (Model Context Protocol) server. Actions: "
            "status (show server info and exposed tools), "
            "expose (add a tool to MCP), "
            "hide (remove a tool from MCP), "
            "handle (process an MCP request), "
            "manifest (generate MCP tool manifest). "
            "Allows external AI agents to use Mikalia's tools."
        )

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: status, expose, hide, handle, manifest",
                    "enum": ["status", "expose", "hide", "handle", "manifest"],
                },
                "tool_name": {
                    "type": "string",
                    "description": "Tool name to expose/hide",
                },
                "request": {
                    "type": "string",
                    "description": "MCP JSON-RPC request to handle",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str,
        tool_name: str = "",
        request: str = "",
        **_: Any,
    ) -> ToolResult:
        if action == "status":
            return self._status()
        elif action == "expose":
            return self._expose(tool_name)
        elif action == "hide":
            return self._hide(tool_name)
        elif action == "handle":
            return self._handle(request)
        elif action == "manifest":
            return self._manifest()
        else:
            return ToolResult(success=False, error=f"Accion desconocida: {action}")

    def _status(self) -> ToolResult:
        available = self._registry.list_tools() if self._registry else []
        return ToolResult(
            success=True,
            output=(
                f"=== MCP Server ===\n"
                f"Nombre: {self._server_info['name']}\n"
                f"Version: {self._server_info['version']}\n"
                f"Protocol: {self._server_info['protocol_version']}\n"
                f"Tools expuestos: {len(self._exposed_tools)}\n"
                f"Tools disponibles: {len(available)}\n"
                f"\nExpuestos: {', '.join(self._exposed_tools) or '(ninguno)'}"
            ),
        )

    def _expose(self, tool_name: str) -> ToolResult:
        if not tool_name:
            return ToolResult(success=False, error="Nombre de tool requerido")

        if self._registry and tool_name not in self._registry.list_tools():
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' no existe en el registry",
            )

        if tool_name in self._exposed_tools:
            return ToolResult(
                success=True,
                output=f"Tool '{tool_name}' ya esta expuesto",
            )

        # No exponer tools peligrosos
        dangerous = {"shell_exec", "file_write", "git_push", "git_commit"}
        if tool_name in dangerous:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' es peligroso para exponer via MCP",
            )

        self._exposed_tools.append(tool_name)
        logger.info(f"MCP: tool expuesto: {tool_name}")
        return ToolResult(
            success=True,
            output=f"Tool '{tool_name}' expuesto via MCP\nTotal expuestos: {len(self._exposed_tools)}",
        )

    def _hide(self, tool_name: str) -> ToolResult:
        if tool_name not in self._exposed_tools:
            return ToolResult(success=False, error=f"Tool '{tool_name}' no esta expuesto")

        self._exposed_tools.remove(tool_name)
        return ToolResult(success=True, output=f"Tool '{tool_name}' removido de MCP")

    def _handle(self, request_str: str) -> ToolResult:
        """Procesa un request MCP (JSON-RPC 2.0)."""
        if not request_str:
            return ToolResult(success=False, error="Request JSON requerido")

        try:
            req = json.loads(request_str)
        except json.JSONDecodeError:
            return self._mcp_error(-32700, "Parse error")

        method = req.get("method", "")
        req_id = req.get("id", 1)
        params = req.get("params", {})

        if method == "initialize":
            return self._mcp_response(req_id, {
                "protocolVersion": MCP_VERSION,
                "serverInfo": self._server_info,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
            })

        elif method == "tools/list":
            tools = self._get_exposed_definitions()
            return self._mcp_response(req_id, {"tools": tools})

        elif method == "tools/call":
            return self._handle_tool_call(req_id, params)

        else:
            return self._mcp_error(-32601, f"Method not found: {method}", req_id)

    def _handle_tool_call(self, req_id: int, params: dict) -> ToolResult:
        """Ejecuta una llamada a tool via MCP."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._exposed_tools:
            return self._mcp_error(
                -32602, f"Tool '{tool_name}' not available via MCP", req_id
            )

        if not self._registry:
            return self._mcp_error(-32603, "No registry available", req_id)

        result = self._registry.execute(tool_name, arguments)

        content = []
        if result.success:
            content.append({"type": "text", "text": result.output or ""})
        else:
            content.append({"type": "text", "text": result.error or "Unknown error"})

        return self._mcp_response(req_id, {
            "content": content,
            "isError": not result.success,
        })

    def _manifest(self) -> ToolResult:
        """Genera el manifiesto MCP completo."""
        tools = self._get_exposed_definitions()
        manifest = {
            "server": self._server_info,
            "tools": tools,
        }
        return ToolResult(
            success=True,
            output=json.dumps(manifest, indent=2, ensure_ascii=False),
        )

    def _get_exposed_definitions(self) -> list[dict]:
        """Obtiene definiciones de tools expuestos en formato MCP."""
        if not self._registry:
            return []

        tools = []
        for name in self._exposed_tools:
            tool = self._registry.get(name)
            if tool:
                defn = tool.to_claude_definition()
                tools.append({
                    "name": defn["name"],
                    "description": defn.get("description", ""),
                    "inputSchema": defn.get("input_schema", {}),
                })
        return tools

    def _mcp_response(self, req_id: int, result: dict) -> ToolResult:
        """Formatea respuesta MCP."""
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }
        return ToolResult(
            success=True,
            output=json.dumps(response, indent=2, ensure_ascii=False),
        )

    def _mcp_error(
        self, code: int, message: str, req_id: int = 1
    ) -> ToolResult:
        """Formatea error MCP."""
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
        return ToolResult(
            success=False,
            error=json.dumps(response, ensure_ascii=False),
        )
