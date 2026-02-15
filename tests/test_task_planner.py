"""
test_task_planner.py — Tests para el planificador de tareas.

Verifica que TaskPlanner pueda:
- Clasificar tareas correctamente por keywords
- Parsear planes JSON de Claude
- Manejar respuestas inválidas con defaults seguros
"""

import pytest

from mikalia.agent.task_planner import (
    TaskPlanner,
    TaskType,
    ComplexityLevel,
    TaskPlan,
    Step,
)


class TestTaskClassification:
    """Tests para clasificación rápida de tareas."""

    @pytest.fixture
    def planner(self):
        """TaskPlanner sin client (solo para clasificación)."""
        # Usamos None como client ya que classify_task no lo usa
        return TaskPlanner(client=None)

    def test_fix_classification(self, planner):
        """Keywords de fix se detectan correctamente."""
        assert planner.classify_task("Fix the bug in login") == TaskType.FIX
        assert planner.classify_task("Error handling is broken") == TaskType.FIX
        assert planner.classify_task("Crash when clicking submit") == TaskType.FIX

    def test_docs_classification(self, planner):
        """Keywords de docs se detectan correctamente."""
        assert planner.classify_task("Update the README") == TaskType.DOCS
        assert planner.classify_task("Add documentation for API") == TaskType.DOCS
        assert planner.classify_task("Update comments in module") == TaskType.DOCS

    def test_security_classification(self, planner):
        """Keywords de security se detectan (prioridad alta)."""
        assert planner.classify_task("Security vulnerability in auth") == TaskType.SECURITY
        assert planner.classify_task("Fix SQL injection issue") == TaskType.SECURITY

    def test_post_classification(self, planner):
        """Keywords de post se detectan correctamente."""
        assert planner.classify_task("Write a blog post about AI") == TaskType.POST

    def test_feat_default(self, planner):
        """Sin keywords claros, default a FEAT."""
        assert planner.classify_task("Add user validation to forms") == TaskType.FEAT
        assert planner.classify_task("Implement dark mode") == TaskType.FEAT


class TestTaskPlan:
    """Tests para la dataclass TaskPlan."""

    def test_files_to_modify_consolidated(self):
        """Lista de archivos se consolida sin duplicados."""
        plan = TaskPlan(
            task_description="Test",
            task_type=TaskType.FEAT,
            steps=[
                Step(1, "Step 1", files=["a.py", "b.py"]),
                Step(2, "Step 2", files=["b.py", "c.py"]),
            ],
        )
        assert plan.files_to_modify == ["a.py", "b.py", "c.py"]

    def test_is_safe_with_no_check(self):
        """Sin safety check, is_safe es False."""
        plan = TaskPlan(
            task_description="Test",
            task_type=TaskType.FEAT,
        )
        assert not plan.is_safe

    def test_is_safe_with_allowed_check(self):
        """Con safety check allowed, is_safe es True."""
        from mikalia.agent.safety import SafetyResult, Severity
        plan = TaskPlan(
            task_description="Test",
            task_type=TaskType.FEAT,
            safety_check=SafetyResult(
                allowed=True,
                reason="OK",
                severity=Severity.OK,
            ),
        )
        assert plan.is_safe

    def test_is_safe_with_blocked_check(self):
        """Con safety check blocked, is_safe es False."""
        from mikalia.agent.safety import SafetyResult, Severity
        plan = TaskPlan(
            task_description="Test",
            task_type=TaskType.FEAT,
            safety_check=SafetyResult(
                allowed=False,
                reason="Blocked",
                severity=Severity.BLOCKED,
            ),
        )
        assert not plan.is_safe


class TestParsePlan:
    """Tests para el parseo de planes JSON."""

    @pytest.fixture
    def planner(self):
        return TaskPlanner(client=None)

    def test_parse_valid_plan(self, planner):
        """JSON válido se parsea correctamente."""
        response = '''{
            "task_type": "feat",
            "steps": [
                {"number": 1, "description": "Add validation", "files": ["app.py"], "action": "modify"},
                {"number": 2, "description": "Add tests", "files": ["tests/test_app.py"], "action": "create"}
            ],
            "complexity": "medium",
            "estimated_files": 2,
            "estimated_lines": 80,
            "branch_slug": "add-validation"
        }'''

        plan = planner._parse_plan(response, "Add validation")

        assert plan.task_type == TaskType.FEAT
        assert len(plan.steps) == 2
        assert plan.complexity == ComplexityLevel.MEDIUM
        assert plan.branch_name == "mikalia/feat/add-validation"
        assert plan.estimated_files == 2

    def test_parse_invalid_json_returns_safe_default(self, planner):
        """JSON inválido retorna defaults seguros."""
        plan = planner._parse_plan("not json at all", "Some task")

        assert plan.task_type == TaskType.FEAT
        assert plan.complexity == ComplexityLevel.NEEDS_HUMAN
        assert len(plan.steps) == 0

    def test_parse_with_code_fences(self, planner):
        """JSON envuelto en code fences se limpia."""
        response = '```json\n{"task_type": "fix", "steps": [], "complexity": "low", "estimated_files": 1, "estimated_lines": 10, "branch_slug": "fix-bug"}\n```'

        plan = planner._parse_plan(response, "Fix bug")
        assert plan.task_type == TaskType.FIX
        assert plan.complexity == ComplexityLevel.LOW
