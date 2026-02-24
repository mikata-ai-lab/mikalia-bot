"""
skill_creator.py — Sistema de auto-creacion de skills para Mikalia.

Permite a Mikalia escribir nuevos tools en Python, validarlos,
y registrarlos en caliente (hot-reload) en el ToolRegistry.

Flujo:
    1. Mikalia genera codigo Python para un tool nuevo
    2. SkillCreator valida seguridad (no imports peligrosos)
    3. Guarda en mikalia/tools/custom/<name>.py
    4. Importa dinamicamente y registra en ToolRegistry
    5. Persiste metadata en tabla `skills`

Uso:
    creator = SkillCreator(memory, registry)
    result = creator.create_skill(name, description, code)
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import sys
from pathlib import Path

from mikalia.core.memory import MemoryManager
from mikalia.tools.base import BaseTool, ToolResult
from mikalia.tools.registry import ToolRegistry
from mikalia.utils.logger import get_logger

logger = get_logger("mikalia.core.skill_creator")

# Patrones peligrosos que NO deben estar en el codigo de skills
DANGEROUS_PATTERNS = [
    r"\bos\.system\b",
    r"\bsubprocess\.(call|run|Popen|check_output)\b.*shell\s*=\s*True",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\b__import__\b",
    r"\bopen\s*\(.*['\"]w['\"]",  # Escritura a archivos arbitrarios
    r"\bshutil\.rmtree\b",
    r"\brm\s+-rf\b",
    r"\bDROP\s+TABLE\b",
    r"\bDELETE\s+FROM\b(?!.*WHERE)",  # DELETE sin WHERE
    r"\.env\b",
    r"\bsecrets?\b",
    r"\bpassword\b",
    r"\bapi_key\b",
    r"\btoken\b(?!.*ize)",  # "token" pero no "tokenize"
]

# Imports permitidos (whitelist)
ALLOWED_IMPORTS = {
    "__future__",
    "json", "re", "datetime", "time", "math", "hashlib",
    "urllib", "urllib.request", "urllib.parse",
    "pathlib", "typing", "dataclasses", "collections",
    "mikalia.tools.base", "mikalia.utils.logger",
}

CUSTOM_TOOLS_DIR = Path(__file__).parent.parent / "tools" / "custom"


class SkillCreator:
    """
    Crea y registra skills (tools) nuevos para Mikalia.

    Valida seguridad, guarda archivos, importa dinamicamente
    y registra en el ToolRegistry.
    """

    def __init__(
        self,
        memory: MemoryManager,
        registry: ToolRegistry,
    ) -> None:
        self._memory = memory
        self._registry = registry

    def create_skill(
        self,
        name: str,
        description: str,
        code: str,
    ) -> ToolResult:
        """
        Crea un skill nuevo.

        Args:
            name: Nombre del tool (snake_case, ej: "weather_check").
            description: Descripcion breve del tool.
            code: Codigo Python completo de la clase del tool.

        Returns:
            ToolResult con exito o error.
        """
        # 1. Validar nombre
        if not re.match(r'^[a-z][a-z0-9_]{2,30}$', name):
            return ToolResult(
                success=False,
                error=(
                    f"Nombre invalido: '{name}'. "
                    "Usa snake_case, 3-30 chars, sin mayusculas."
                ),
            )

        # 2. Validar seguridad del codigo
        safety = self._validate_safety(code)
        if not safety["safe"]:
            return ToolResult(
                success=False,
                error=f"Codigo rechazado por seguridad: {safety['reason']}",
            )

        # 3. Validar que el codigo tiene una clase BaseTool
        if "BaseTool" not in code or "def execute" not in code:
            return ToolResult(
                success=False,
                error="El codigo debe tener una clase que herede de BaseTool con metodo execute().",
            )

        # 4. Guardar archivo
        file_path = CUSTOM_TOOLS_DIR / f"{name}.py"
        try:
            CUSTOM_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
            file_path.write_text(code, encoding="utf-8")
            logger.info(f"Skill guardado: {file_path}")
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Error guardando archivo: {e}",
            )

        # 5. Importar dinamicamente
        try:
            tool_instance = self._dynamic_import(name, file_path)
        except Exception as e:
            # Limpiar archivo si falla import
            file_path.unlink(missing_ok=True)
            return ToolResult(
                success=False,
                error=f"Error importando skill: {e}",
            )

        # 6. Registrar en ToolRegistry
        self._registry.register(tool_instance)

        # 7. Persistir en DB
        try:
            self._save_to_db(name, description, str(file_path))
        except Exception as e:
            logger.warning(f"No se pudo guardar en DB: {e}")

        logger.success(f"Skill '{name}' creado y registrado!")
        return ToolResult(
            success=True,
            output=(
                f"Skill '{name}' creado exitosamente!\n"
                f"Archivo: {file_path}\n"
                f"Ya puedes usarlo como herramienta."
            ),
        )

    def load_custom_skills(self) -> int:
        """
        Carga todos los skills custom del directorio.

        Se llama al iniciar Mikalia para cargar skills persistidos.

        Returns:
            Numero de skills cargados.
        """
        if not CUSTOM_TOOLS_DIR.exists():
            return 0

        count = 0
        for py_file in CUSTOM_TOOLS_DIR.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            name = py_file.stem
            try:
                tool = self._dynamic_import(name, py_file)
                self._registry.register(tool)
                count += 1
                logger.info(f"Skill custom cargado: {name}")
            except Exception as e:
                logger.warning(f"No se pudo cargar skill '{name}': {e}")

        if count > 0:
            logger.success(f"{count} skills custom cargados.")
        return count

    def list_custom_skills(self) -> list[dict]:
        """Lista skills custom desde la DB."""
        conn = self._memory._get_connection()
        try:
            cursor = conn.execute(
                "SELECT name, description, is_enabled, times_used, "
                "success_rate, created_at FROM skills ORDER BY name"
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    # ================================================================
    # Seguridad
    # ================================================================

    def _validate_safety(self, code: str) -> dict:
        """
        Valida que el codigo no tiene patrones peligrosos.

        Returns:
            Dict con "safe": bool y "reason": str si no es safe.
        """
        # Verificar patrones peligrosos
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return {
                    "safe": False,
                    "reason": f"Patron peligroso detectado: {pattern}",
                }

        # Verificar imports
        import_lines = re.findall(
            r'^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))',
            code,
            re.MULTILINE,
        )
        for groups in import_lines:
            module = groups[0] or groups[1]
            # Permitir imports de mikalia y whitelist
            if (
                module not in ALLOWED_IMPORTS
                and not module.startswith("mikalia.")
            ):
                return {
                    "safe": False,
                    "reason": (
                        f"Import no permitido: '{module}'. "
                        f"Permitidos: {', '.join(sorted(ALLOWED_IMPORTS))}"
                    ),
                }

        return {"safe": True, "reason": ""}

    # ================================================================
    # Import dinamico
    # ================================================================

    def _dynamic_import(self, name: str, file_path: Path) -> BaseTool:
        """
        Importa un modulo Python dinamicamente y retorna la instancia del tool.

        Busca la primera clase que herede de BaseTool en el modulo.
        """
        module_name = f"mikalia.tools.custom.{name}"

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"No se pudo crear spec para {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Buscar clase que herede de BaseTool
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseTool)
                and attr is not BaseTool
            ):
                return attr()

        raise ImportError(
            f"No se encontro clase BaseTool en {file_path}"
        )

    # ================================================================
    # Persistencia
    # ================================================================

    def _save_to_db(self, name: str, description: str, path: str) -> None:
        """Guarda metadata del skill en la DB."""
        conn = self._memory._get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO skills "
                "(name, description, skill_md_path, is_enabled) "
                "VALUES (?, ?, ?, 1)",
                (name, description, path),
            )
            conn.commit()
        finally:
            conn.close()
