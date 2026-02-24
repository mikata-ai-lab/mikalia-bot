"""
registry.py — Registro central de tools de Mikalia.

Descubre, registra y ejecuta tools. Genera las definiciones
que Claude API necesita para tool_use.

Uso:
    from mikalia.tools.registry import ToolRegistry
    registry = ToolRegistry.with_defaults()
    definitions = registry.get_tool_definitions()
    result = registry.execute("file_read", {"path": "README.md"})
"""

from __future__ import annotations

from typing import Any

from mikalia.tools.base import BaseTool, ToolResult
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.tools.registry")


class ToolRegistry:
    """
    Registro central de tools disponibles.

    Descubre, registra y ejecuta tools. Genera las definiciones
    que Claude API necesita para tool_use.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registra un tool en el registry."""
        self._tools[tool.name] = tool
        logger.info(f"Tool registrado: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        """Obtiene un tool por nombre."""
        return self._tools.get(name)

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """
        Genera las definiciones de tools para Claude API.

        Returns:
            Lista de dicts compatibles con el parametro `tools`
            de messages.create().
        """
        return [tool.to_claude_definition() for tool in self._tools.values()]

    def execute(self, tool_name: str, params: dict[str, Any]) -> ToolResult:
        """
        Ejecuta un tool por nombre con los parametros dados.

        Args:
            tool_name: Nombre del tool a ejecutar.
            params: Parametros para el tool.

        Returns:
            ToolResult con el resultado de la ejecucion.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool no encontrado: '{tool_name}'. "
                f"Disponibles: {', '.join(self._tools.keys())}",
            )

        try:
            return tool.execute(**params)
        except Exception as e:
            logger.error(f"Error ejecutando tool '{tool_name}': {e}")
            return ToolResult(success=False, error=str(e))

    def list_tools(self) -> list[str]:
        """Lista los nombres de todos los tools registrados."""
        return list(self._tools.keys())

    @classmethod
    def with_defaults(
        cls,
        memory: Any = None,
        vector_memory: Any = None,
        client: Any = None,
    ) -> ToolRegistry:
        """
        Crea un registry con los tools por defecto de Mikalia.

        Args:
            memory: MemoryManager para memory tools (opcional).
            vector_memory: VectorMemory para busqueda semantica (opcional).
            client: MikaliaClient para tools que usan Claude API (opcional).
        """
        registry = cls()

        # === Core tools (siempre disponibles) ===
        from mikalia.tools.file_ops import (
            FileReadTool,
            FileWriteTool,
            FileListTool,
        )
        from mikalia.tools.shell import ShellExecTool
        from mikalia.tools.git_ops import (
            GitStatusTool,
            GitDiffTool,
            GitLogTool,
        )
        from mikalia.tools.web_fetch import WebFetchTool
        from mikalia.tools.blog_post import BlogPostTool
        from mikalia.tools.browser import BrowserTool
        from mikalia.tools.voice import TextToSpeechTool, SpeechToTextTool
        from mikalia.tools.image_gen import ImageGenerationTool
        from mikalia.tools.github_tools import (
            GitCommitTool,
            GitPushTool,
            GitBranchTool,
            GitHubPRTool,
        )

        registry.register(FileReadTool())
        registry.register(FileWriteTool())
        registry.register(FileListTool())
        registry.register(ShellExecTool())
        registry.register(GitStatusTool())
        registry.register(GitDiffTool())
        registry.register(GitLogTool())
        registry.register(WebFetchTool())
        registry.register(BlogPostTool())
        registry.register(BrowserTool())
        registry.register(GitCommitTool())
        registry.register(GitPushTool())
        registry.register(GitBranchTool())
        registry.register(GitHubPRTool())
        registry.register(TextToSpeechTool())
        registry.register(SpeechToTextTool())
        registry.register(ImageGenerationTool())

        # === Extended tools (sin dependencias) ===
        from mikalia.tools.api_fetch import ApiFetchTool
        from mikalia.tools.system_monitor import SystemMonitorTool
        from mikalia.tools.weather import WeatherTool
        from mikalia.tools.email_sender import EmailSenderTool
        from mikalia.tools.code_sandbox import CodeSandboxTool
        from mikalia.tools.pomodoro import PomodoroTool
        from mikalia.tools.data_viz import DataVisualizationTool
        from mikalia.tools.csv_analyzer import CsvAnalyzerTool
        from mikalia.tools.pdf_report import PdfReportTool
        from mikalia.tools.rss_reader import RssFeedTool

        registry.register(ApiFetchTool())
        registry.register(SystemMonitorTool())
        registry.register(WeatherTool())
        registry.register(EmailSenderTool())
        registry.register(CodeSandboxTool())
        registry.register(PomodoroTool())
        registry.register(DataVisualizationTool())
        registry.register(CsvAnalyzerTool())
        registry.register(PdfReportTool())
        registry.register(RssFeedTool())

        # === AI-powered tools (usan Claude API, graceful sin client) ===
        from mikalia.tools.translate import TranslateTool
        from mikalia.tools.url_summarizer import UrlSummarizerTool
        from mikalia.tools.pr_reviewer import PrReviewerTool
        from mikalia.tools.multi_model import MultiModelTool

        registry.register(TranslateTool(client))
        registry.register(UrlSummarizerTool(client))
        registry.register(PrReviewerTool(client))
        registry.register(MultiModelTool(client))

        # === Memory tools (requieren MemoryManager) ===
        if memory is not None:
            from mikalia.tools.memory_tools import (
                SearchMemoryTool,
                AddFactTool,
                UpdateGoalTool,
                ListGoalsTool,
            )
            from mikalia.tools.daily_brief import DailyBriefTool
            from mikalia.tools.habit_tracker import HabitTrackerTool
            from mikalia.tools.conversation_analytics import ConversationAnalyticsTool
            from mikalia.tools.expense_tracker import ExpenseTrackerTool
            from mikalia.tools.workflow_triggers import WorkflowTriggersTool
            from mikalia.tools.rag_pipeline import RagPipelineTool
            from mikalia.tools.mcp_server import McpServerTool

            registry.register(SearchMemoryTool(memory, vector_memory))
            registry.register(AddFactTool(memory, vector_memory))
            registry.register(UpdateGoalTool(memory))
            registry.register(ListGoalsTool(memory))
            registry.register(DailyBriefTool(memory))
            registry.register(HabitTrackerTool(memory))
            registry.register(ConversationAnalyticsTool(memory))
            registry.register(ExpenseTrackerTool(memory))
            registry.register(WorkflowTriggersTool(memory))
            registry.register(RagPipelineTool(client, vector_memory))
            registry.register(McpServerTool(registry))

            # Skill tools (auto-creacion de herramientas)
            from mikalia.core.skill_creator import SkillCreator
            from mikalia.tools.skill_tools import (
                CreateSkillTool,
                ListSkillsTool,
            )
            creator = SkillCreator(memory, registry)
            registry.register(CreateSkillTool(creator))
            registry.register(ListSkillsTool(creator))

            # Cargar skills custom existentes
            creator.load_custom_skills()

        return registry
