"""
agent.py — El corazon de Mikalia Core: el agent loop.

Orquesta el ciclo completo:
RECEIVE -> CONTEXT -> LLM (con tools) -> TOOLS -> RESPOND -> PERSIST -> EVALUATE

Este es un agent loop SINCRONO (Phase 1). La migracion a async
es un objetivo futuro.

Uso:
    from mikalia.core.agent import MikaliaAgent
    agent = MikaliaAgent()
    response = agent.process_message("Hola Mikalia", channel="cli")
"""

from __future__ import annotations

import json

from mikalia.config import AppConfig, load_config
from mikalia.core.context import ContextBuilder
from mikalia.core.memory import MemoryManager
from mikalia.generation.client import MikaliaClient
from mikalia.tools.base import ToolResult
from mikalia.tools.registry import ToolRegistry
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.core.agent")


class MikaliaAgent:
    """
    Agente autonomo principal de Mikalia Core.

    Procesa mensajes a traves del ciclo completo:
    contexto -> LLM con tools -> ejecucion de tools -> respuesta -> persistencia.

    Args:
        config: Configuracion de la app (auto-carga si None).
        memory: MemoryManager (auto-crea si None).
        client: MikaliaClient (auto-crea si None).
        tool_registry: ToolRegistry (auto-crea con defaults si None).
    """

    MAX_TOOL_ROUNDS = 20  # Safety: limite de rondas de tool calls
    COMPRESSION_THRESHOLD = 30  # Mensajes antes de comprimir
    MESSAGES_TO_KEEP = 10  # Mensajes recientes a preservar

    def __init__(
        self,
        config: AppConfig | None = None,
        memory: MemoryManager | None = None,
        client: MikaliaClient | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self._config = config or load_config()
        self._memory = memory or MemoryManager()
        self._client = client or MikaliaClient(
            api_key=self._config.anthropic_api_key,
            model=self._config.mikalia.model,
        )
        self._tools = tool_registry or ToolRegistry.with_defaults(memory=self._memory)
        self._context_builder = ContextBuilder(
            memory=self._memory,
            tool_registry=self._tools,
        )
        self._current_session: str | None = None

    def process_message(
        self,
        message: str,
        channel: str = "cli",
        session_id: str | None = None,
    ) -> str:
        """
        Procesa un mensaje del usuario y retorna la respuesta de Mikalia.

        Flujo completo:
        1. Crear/obtener sesion
        2. Persistir mensaje del usuario
        3. Construir contexto (system prompt + historial)
        4. Llamar a Claude con tools
        5. Loop de tool calls hasta respuesta final
        6. Persistir respuesta
        7. Retornar texto

        Args:
            message: Texto del mensaje del usuario.
            channel: Canal de origen ('cli', 'telegram', etc.)
            session_id: ID de sesion existente (o None para crear nueva).

        Returns:
            Texto de la respuesta de Mikalia.
        """
        # 1. Session
        if session_id is None:
            session_id = self._memory.create_session(channel)
        self._current_session = session_id

        # 2. Persist user message
        self._memory.add_message(session_id, channel, "user", message)

        # 3. Build context
        context = self._context_builder.build(
            session_id=session_id,
            channel=channel,
        )

        # El mensaje del usuario ya esta en el historial de la sesion
        # que _build_messages() recupera, asi que no lo pasamos como
        # user_message para evitar duplicados

        # 4. Call Claude with tools
        response = self._client.chat_with_tools(
            messages=context.messages,
            tools=self._tools.get_tool_definitions() or None,
            system=context.system_prompt,
            temperature=self._config.mikalia.generation_temperature,
            max_tokens=self._config.mikalia.max_tokens,
        )

        # 5. Tool call loop
        rounds = 0
        while response.has_tool_use and rounds < self.MAX_TOOL_ROUNDS:
            rounds += 1
            logger.info(
                f"Tool round {rounds}: "
                f"{len(response.tool_calls)} tool(s)"
            )

            # Execute each tool call
            tool_results = []
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call["id"],
                    "content": result.output if result.success else f"Error: {result.error}",
                    "is_error": not result.success,
                })

            # Add assistant response (with tool_use blocks) and results
            context.messages.append({
                "role": "assistant",
                "content": response.raw_content,
            })
            context.messages.append({
                "role": "user",
                "content": tool_results,
            })

            # Compress if conversation is getting long
            context.messages = self._maybe_compress(context.messages)

            # Continue conversation
            response = self._client.chat_with_tools(
                messages=context.messages,
                tools=self._tools.get_tool_definitions() or None,
                system=context.system_prompt,
                temperature=self._config.mikalia.generation_temperature,
                max_tokens=self._config.mikalia.max_tokens,
            )

        # 6. Persist assistant response
        self._memory.add_message(
            session_id,
            channel,
            "assistant",
            response.content,
            tokens_used=response.input_tokens + response.output_tokens,
        )

        # 7. Return
        logger.info(
            f"Respuesta generada "
            f"({response.input_tokens}+{response.output_tokens} tokens, "
            f"{rounds} tool rounds)"
        )
        return response.content

    def _execute_tool(self, tool_call: dict) -> ToolResult:
        """Ejecuta un tool call y retorna el resultado."""
        name = tool_call["name"]
        params = tool_call.get("input", {})

        # Log truncado para no llenar la consola
        params_str = json.dumps(params, ensure_ascii=False)
        if len(params_str) > 100:
            params_str = params_str[:100] + "..."
        logger.info(f"Tool: {name}({params_str})")

        result = self._tools.execute(name, params)

        if result.success:
            output_preview = result.output[:80] + "..." if len(result.output) > 80 else result.output
            logger.success(f"Tool {name}: OK — {output_preview}")
        else:
            logger.warning(f"Tool {name}: Error — {result.error}")

        return result

    def _maybe_compress(self, messages: list[dict]) -> list[dict]:
        """
        Comprime mensajes viejos en un resumen si la lista es muy larga.

        Mantiene los ultimos MESSAGES_TO_KEEP mensajes intactos y reemplaza
        los anteriores con un resumen generado por Claude.

        Args:
            messages: Lista actual de mensajes.

        Returns:
            Lista de mensajes (posiblemente comprimida).
        """
        if len(messages) <= self.COMPRESSION_THRESHOLD:
            return messages

        logger.info(
            f"Comprimiendo conversacion: {len(messages)} mensajes "
            f"(threshold: {self.COMPRESSION_THRESHOLD})"
        )

        old_messages = messages[:-self.MESSAGES_TO_KEEP]
        recent_messages = messages[-self.MESSAGES_TO_KEEP:]

        # Construir texto para resumir
        old_text_parts = []
        for msg in old_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                old_text_parts.append(f"{role}: {content[:200]}")
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("content", item.get("text", ""))
                        old_text_parts.append(f"{role}: {str(text)[:200]}")

        old_text = "\n".join(old_text_parts)

        try:
            summary_response = self._client.generate(
                user_prompt=(
                    "Summarize this conversation context in 2-3 sentences. "
                    "Focus on: what was discussed, what tools were used, "
                    "what decisions were made, and any important results.\n\n"
                    f"{old_text}"
                ),
                system_override=(
                    "You are a conversation summarizer. Be concise and factual. "
                    "Output only the summary, nothing else."
                ),
                temperature=0.3,
                max_tokens=300,
            )
            summary = summary_response.content
        except Exception as e:
            logger.warning(f"Error comprimiendo: {e}. Continuando sin comprimir.")
            return messages

        # Construir lista comprimida con roles alternantes validos
        compressed: list[dict] = [
            {"role": "user", "content": f"[Previous conversation summary]: {summary}"},
            {"role": "assistant", "content": "Understood, I have the context. Continuing."},
        ]

        # Asegurar alternancia valida con los mensajes recientes
        if recent_messages and recent_messages[0].get("role") == "assistant":
            compressed.append({"role": "user", "content": "[continuation]"})

        compressed.extend(recent_messages)

        logger.info(
            f"Compresion exitosa: {len(messages)} -> {len(compressed)} mensajes"
        )
        return compressed

    @property
    def session_id(self) -> str | None:
        """ID de la sesion actual."""
        return self._current_session

    @property
    def memory(self) -> MemoryManager:
        """Acceso al MemoryManager (para /goals, /facts, etc.)"""
        return self._memory
