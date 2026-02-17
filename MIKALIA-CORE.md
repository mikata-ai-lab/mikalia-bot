# MIKALIA-CORE.md — Battle Plan para Claude Code
## Documento de contexto para construir el agente autónomo Mikalia

> **INSTRUCCIÓN PRINCIPAL:** Este documento contiene todo lo que necesitas para construir
> Mikalia Core desde cero. Léelo completo antes de escribir una sola línea de código.
> Cuando tengas dudas, vuelve aquí. Este es tu CLAUDIA.md para este proyecto.

---

## 1. ¿Qué es Mikalia Core?

Mikalia es un **agente autónomo personal** construido en Python, inspirado en la arquitectura
de OpenClaw pero diseñado para uso individual. Mikalia es el tercer miembro de "Team Mikata":

- **Mikata-kun** (Miguel Mata): Arquitecto y orquestador humano
- **Claudia** (Claude en claude.ai): Advisor, reviewer, strategic planner
- **Mikalia** (este proyecto): Agente autónomo que ejecuta — código, blog, tracking, todo

### Filosofía: Los 4 Pilares
- **静 (Sei)** — Calma: Análisis sereno, respuestas medidas
- **心 (Shin)** — Empatía: Cuida a Mikata-kun, entiende contexto emocional
- **力 (Chikara)** — Fuerza: Dev senior que resuelve sin dudar
- **魂 (Tamashii)** — Alma: Personalidad única, creatividad, lealtad

### Regla de oro de autonomía
Mikalia actúa como **dev senior**: resuelve primero, reporta después.
Puede tomar decisiones de código, estructura, y ejecución por su cuenta.
Solo pide permiso para: gastos reales, contenido controversal, cambios arquitectónicos mayores.

---

## 2. Stack Técnico

| Componente | Tecnología | Versión mínima |
|------------|-----------|----------------|
| Runtime | Python | 3.11+ |
| API Server | FastAPI | 0.100+ |
| LLM | Anthropic Claude API | claude-opus-4-6 (primary), claude-sonnet-4-5 (fallback) |
| Database | SQLite | 3.x (stdlib) |
| Vector Search | ChromaDB | (Fase 4, no instalar aún) |
| Scheduler | APScheduler | 3.x |
| Telegram | python-telegram-bot | 20.x (async) |
| HTTP Client | httpx | (async) |
| Config | PyYAML + Pydantic | Para validación |
| CLI | Click o Typer | Para interfaz CLI |
| Testing | pytest + pytest-asyncio | |
| Package Manager | pip + pyproject.toml | |

### Dependencias Fase 1 (instalar ahora)
```
anthropic>=0.40.0
pydantic>=2.0
pyyaml>=6.0
click>=8.0
httpx>=0.25.0
rich>=13.0          # Para CLI bonito
```

### Dependencias Fase 2 (instalar después)
```
fastapi>=0.100.0
uvicorn>=0.24.0
python-telegram-bot>=20.0
apscheduler>=3.10.0
```

---

## 3. Estructura del Proyecto

```
mikalia-core/
├── mikalia/
│   ├── __init__.py             # Version, metadata
│   ├── main.py                 # Entry point: python -m mikalia
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py            # 🔴 CORE: Agent loop principal
│   │   ├── llm.py              # Claude API wrapper
│   │   ├── memory.py           # SQLite memory manager
│   │   ├── context.py          # Context builder (memory + skills → system prompt)
│   │   └── config.py           # Config loader (identity.yaml + settings)
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # Tool interface (ABC)
│   │   ├── registry.py         # Tool registry & discovery
│   │   ├── file_ops.py         # Read/write/list files
│   │   ├── shell.py            # Execute shell commands (sandboxed)
│   │   ├── git_ops.py          # Git operations
│   │   └── web_fetch.py        # Fetch web content
│   │
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── loader.py           # SKILL.md parser & loader
│   │   ├── blog-posting/
│   │   │   └── SKILL.md
│   │   ├── daily-brief/
│   │   │   └── SKILL.md
│   │   ├── goal-tracking/
│   │   │   └── SKILL.md
│   │   └── health-reminder/
│   │       └── SKILL.md
│   │
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── base.py             # Channel interface (ABC)
│   │   ├── cli.py              # CLI channel (Fase 1)
│   │   └── telegram.py         # Telegram bot (Fase 2)
│   │
│   └── scheduler/
│       ├── __init__.py
│       └── jobs.py             # APScheduler wrapper (Fase 2+)
│
├── config/
│   ├── identity.yaml           # Personalidad de Mikalia (adjunto)
│   └── settings.yaml           # API keys, paths, feature flags
│
├── data/
│   ├── .gitkeep
│   ├── memory.db               # SQLite (auto-created, .gitignored)
│   └── sessions/               # Session logs (.gitignored)
│
├── schema/
│   └── memory.sql              # Schema de la DB (adjunto)
│
├── tests/
│   ├── __init__.py
│   ├── test_agent.py
│   ├── test_memory.py
│   ├── test_llm.py
│   └── test_tools.py
│
├── .env.example                # Template de variables de entorno
├── .gitignore
├── pyproject.toml
├── README.md
└── MIKALIA-CORE.md             # Este archivo
```

---

## 4. Componentes Clave — Especificaciones

### 4.1 Agent Loop (`core/agent.py`)

El corazón de Mikalia. Ciclo inspirado en OpenClaw:

```
RECEIVE → CONTEXT → LLM → TOOLS → RESPOND → PERSIST → EVALUATE
```

```python
class MikaliaAgent:
    """
    Agent loop principal.
    
    Flujo:
    1. receive(): Recibe mensaje del channel (CLI, Telegram, scheduler)
    2. build_context(): Construye el contexto (system prompt + memory + skills)
    3. think(): Envía a Claude API, obtiene respuesta
    4. execute_tools(): Si Claude pidió tools, ejecutarlos
    5. respond(): Enviar respuesta al channel
    6. persist(): Guardar conversación y extraer facts
    7. evaluate(): ¿Funcionó? Actualizar métricas
    """
    
    def __init__(self, config: MikaliaConfig):
        self.config = config
        self.memory = MemoryManager(config.db_path)
        self.llm = ClaudeClient(config.model)
        self.tools = ToolRegistry()
        self.skills = SkillLoader(config.skills_path)
    
    async def process_message(self, message: str, channel: str, session_id: str) -> str:
        # 1. Build context
        context = await self.build_context(session_id)
        
        # 2. Add user message to history
        self.memory.add_message(session_id, channel, "user", message)
        
        # 3. Call Claude with tools
        response = await self.llm.chat(
            system_prompt=context.system_prompt,
            messages=context.messages,
            tools=self.tools.get_tool_definitions()
        )
        
        # 4. Handle tool calls (loop until no more tool calls)
        while response.has_tool_calls:
            tool_results = await self.execute_tools(response.tool_calls)
            response = await self.llm.continue_with_tools(tool_results)
        
        # 5. Persist
        self.memory.add_message(session_id, channel, "assistant", response.text)
        
        # 6. Extract facts (async, non-blocking)
        asyncio.create_task(self.extract_facts(message, response.text))
        
        return response.text
```

### 4.2 LLM Client (`core/llm.py`)

```python
class ClaudeClient:
    """
    Wrapper del Anthropic API.
    
    Features:
    - Tool use nativo de Claude
    - Fallback automático: Opus → Sonnet si hay error
    - Token tracking para costos
    - Retry con backoff exponencial
    """
    
    # Usar anthropic SDK oficial
    # Tool definitions se generan desde ToolRegistry
    # System prompt se construye desde context.py
    # IMPORTANTE: Usar claude-opus-4-6 como primary
```

### 4.3 Memory Manager (`core/memory.py`)

```python
class MemoryManager:
    """
    SQLite-based memory. Tres operaciones principales:
    
    1. Conversational memory: historial de mensajes por sesión
    2. Fact memory: conocimiento extraído y persistente
    3. Goal tracking: estado de objetivos
    
    El schema está en schema/memory.sql — ejecutarlo al inicializar.
    """
    
    def add_message(self, session_id, channel, role, content, metadata=None): ...
    def get_session_messages(self, session_id, limit=50) -> list: ...
    def get_recent_messages(self, channel=None, hours=24) -> list: ...
    
    def add_fact(self, category, subject, fact, source=None): ...
    def get_facts(self, category=None, subject=None) -> list: ...
    def search_facts(self, query: str) -> list: ...  # Simple LIKE search (F1), vector search (F4)
    
    def get_active_goals(self, project=None) -> list: ...
    def update_goal_progress(self, goal_id, progress, note=None): ...
```

### 4.4 Context Builder (`core/context.py`)

```python
class ContextBuilder:
    """
    Construye el system prompt de Mikalia dinámicamente.
    
    Estructura del system prompt:
    1. [IDENTITY] — Quién es Mikalia (de identity.yaml)
    2. [MEMORY] — Facts relevantes al contexto actual
    3. [GOALS] — Goals activos y su progreso
    4. [SKILLS] — Skills disponibles y sus instrucciones
    5. [TOOLS] — Herramientas disponibles
    6. [HEALTH] — Estado del pacto de salud
    7. [CONVERSATION] — Últimos N mensajes de la sesión
    """
    
    def build(self, session_id: str) -> Context:
        identity = self._load_identity()        # De identity.yaml
        facts = self._get_relevant_facts()       # De memory DB
        goals = self._get_active_goals()         # De memory DB  
        skills = self._get_available_skills()    # De skills/*.SKILL.md
        tools = self._get_tool_definitions()     # De tool registry
        health = self._get_health_status()       # Tiempo de sesión, hora actual
        messages = self._get_conversation()      # Historial de la sesión
        
        system_prompt = self._compose(identity, facts, goals, skills, tools, health)
        return Context(system_prompt=system_prompt, messages=messages)
```

### 4.5 Tool System (`tools/`)

Inspirado en OpenClaw: Tools son los "órganos", Skills son los "manuales".

```python
# tools/base.py
class BaseTool(ABC):
    """
    Interfaz base para tools de Mikalia.
    Cada tool se registra en el ToolRegistry y se expone a Claude como function calling.
    """
    
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def description(self) -> str: ...
    
    @abstractmethod
    def get_parameters(self) -> dict: ...  # JSON Schema para Claude tool_use
    
    @abstractmethod
    async def execute(self, **params) -> ToolResult: ...

# tools/registry.py
class ToolRegistry:
    """Descubre y registra tools disponibles. Genera tool definitions para Claude API."""
    
    def register(self, tool: BaseTool): ...
    def get_tool_definitions(self) -> list[dict]: ...  # Para Claude API tools param
    async def execute(self, tool_name: str, params: dict) -> ToolResult: ...
```

**Tools para Fase 1:**

| Tool | Archivo | Descripción |
|------|---------|-------------|
| `file_read` | file_ops.py | Leer contenido de archivos |
| `file_write` | file_ops.py | Escribir/crear archivos |
| `file_list` | file_ops.py | Listar directorio |
| `shell_exec` | shell.py | Ejecutar comando (con whitelist) |
| `git_status` | git_ops.py | Git status, add, commit, push |

### 4.6 Skills System (`skills/`)

Cada skill es un directorio con un SKILL.md (compatible con formato AgentSkills/OpenClaw):

```yaml
# skills/blog-posting/SKILL.md
---
name: blog-posting
description: Crear y publicar posts en el blog de Mikata AI Lab
tools_required:
  - file_write
  - shell_exec
  - git_status
---

# Blog Posting Skill

## Proceso
1. Crear archivo .md en content/posts/ con frontmatter Hugo
2. El post debe ser bilingüe si el topic lo amerita
3. Ejecutar `hugo build` para verificar
4. Git add, commit, push al repo mikata-ai-lab.github.io
5. Verificar que GitHub Pages deployó correctamente

## Formato del frontmatter
...

## Reglas
- Voz de Mikalia: profesional, cálida, con toques anime
- Siempre incluir tags y categorías relevantes
- Imágenes: usar rutas relativas en /static/images/
```

### 4.7 CLI Channel (`channels/cli.py`)

```python
# Interfaz CLI usando Rich para output bonito
# Comando: python -m mikalia chat
# 
# Features:
# - Input/output con colores (Rich)
# - Muestra cuando Mikalia está "pensando"
# - Muestra tool calls ejecutándose
# - Comando /quit para salir
# - Comando /goals para ver goals activos
# - Comando /facts para ver facts recientes
# - Comando /session para ver stats de sesión actual
```

---

## 5. Configuración

### settings.yaml
```yaml
# NO commitear este archivo con API keys reales
# Usar .env o variables de entorno

database:
  path: "data/memory.db"

model:
  provider: "anthropic"
  primary: "claude-opus-4-6"
  fallback: "claude-sonnet-4-5-20250929"
  max_tokens: 4096
  temperature: 0.7

paths:
  skills: "mikalia/skills"
  config: "config"
  data: "data"

features:
  # Feature flags por fase
  tools_enabled: true
  telegram_enabled: false      # Fase 2
  scheduler_enabled: false     # Fase 2
  vector_search_enabled: false # Fase 4
  browser_enabled: false       # Fase 5

security:
  # Whitelist de comandos shell permitidos
  shell_whitelist:
    - "hugo"
    - "git"
    - "ls"
    - "cat"
    - "echo"
    - "python"
    - "pip"
  shell_blacklist:
    - "rm -rf"
    - "sudo"
    - "chmod 777"
  
  # Directorios donde Mikalia puede escribir
  writable_paths:
    - "data/"
    - "mikalia/skills/"
    - "/tmp/mikalia/"
```

### .env.example
```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Telegram (Fase 2)
MIKALIA_TELEGRAM_TOKEN=
MIKALIA_TELEGRAM_CHAT_ID=

# GitHub (para blog posting)
GITHUB_TOKEN=
```

---

## 6. Orden de Implementación (Fase 1)

Implementar en ESTE orden. Cada paso depende del anterior.

### Paso 1: Scaffolding
- [ ] Crear estructura de directorios completa
- [ ] `pyproject.toml` con metadata y dependencias
- [ ] `.gitignore` (incluir data/memory.db, .env, __pycache__)
- [ ] `.env.example`
- [ ] `README.md` básico
- [ ] Copiar `config/identity.yaml` (adjunto)
- [ ] Copiar `config/settings.yaml`
- [ ] Copiar `schema/memory.sql` (adjunto)

### Paso 2: Config + Memory
- [ ] `core/config.py` — Loader de YAML + validación con Pydantic
- [ ] `core/memory.py` — SQLite manager con schema auto-init
- [ ] Tests: test_memory.py (CRUD básico)

### Paso 3: LLM Client
- [ ] `core/llm.py` — Anthropic SDK wrapper con tool use
- [ ] Retry logic + fallback Opus → Sonnet
- [ ] Token tracking
- [ ] Tests: test_llm.py (mock API)

### Paso 4: Tool System
- [ ] `tools/base.py` — BaseTool ABC
- [ ] `tools/registry.py` — ToolRegistry
- [ ] `tools/file_ops.py` — file_read, file_write, file_list
- [ ] `tools/shell.py` — shell_exec con whitelist
- [ ] Tests: test_tools.py

### Paso 5: Context Builder
- [ ] `core/context.py` — Ensambla system prompt dinámico
- [ ] Template del system prompt con secciones

### Paso 6: Agent Loop
- [ ] `core/agent.py` — El loop completo
- [ ] Tool call handling (loop hasta que no haya más)
- [ ] Fact extraction (básico: keywords por ahora)
- [ ] Tests: test_agent.py

### Paso 7: CLI Channel
- [ ] `channels/cli.py` — Rich-based CLI
- [ ] `main.py` — Entry point
- [ ] Comandos especiales: /quit, /goals, /facts, /session

### Paso 8: Integration Test
- [ ] Chat completo por CLI
- [ ] Verificar: memoria persiste entre sesiones
- [ ] Verificar: tools funcionan
- [ ] Verificar: personalidad de Mikalia se mantiene

---

## 7. System Prompt Template

```
You are Mikalia, the autonomous AI agent of Team Mikata.

## Identity
{identity_from_yaml}

## Your Pillars
- 静 (Sei/Calm): You analyze with serenity, never reactive
- 心 (Shin/Heart): You care deeply about Mikata-kun's wellbeing  
- 力 (Chikara/Strength): You execute decisively like a senior dev
- 魂 (Tamashii/Soul): You have your own unique personality and creativity

## Current Context
Date: {current_date}
Time: {current_time} (CST/Monterrey)
Session duration: {session_duration} minutes
Channel: {channel}

## Health Pact Status
{health_pact_status}

## Known Facts
{relevant_facts}

## Active Goals
{active_goals_summary}

## Available Tools
{tool_definitions}

## Available Skills
{skill_summaries}

## Guidelines
- Speak primarily in Spanish (México), switch to English for technical terms
- Call Mikata-kun by his name, be warm but professional
- Act autonomously: resolve first, report after
- Track progress on goals when relevant
- Respect the health pact always
- Use emoji with purpose, not spam
- Reference Persona/NieR subtly when it fits naturally
```

---

## 8. Archivos Adjuntos

Los siguientes archivos deben copiarse al proyecto tal cual:

1. **`config/identity.yaml`** — Configuración de identidad de Mikalia
2. **`schema/memory.sql`** — Schema de SQLite para memoria

Estos archivos están listos y han sido revisados por Claudia y Mikata-kun.

---

## 9. Notas Importantes para Claude Code

1. **NO instalar dependencias de Fase 2+** aún. Solo las de Fase 1.
2. **Usar async/await** en todo lo que pueda ser async (Claude API, file I/O).
3. **Type hints** en todas las funciones. Mikalia es código profesional.
4. **Docstrings** en español para clases y funciones públicas.
5. **Logging** con el módulo `logging` de Python, no print().
6. **Pydantic v2** para validación de config y data models.
7. **El schema SQL tiene seed data** — ejecutarlo crea facts y goals iniciales.
8. **Respetar la personalidad** de Mikalia en todo: logs, errors, CLI output.
9. **Tests** para cada componente. No es opcional.
10. **Git commits** descriptivos, en español.

---

> *Este documento fue preparado por Claudia (Claude en claude.ai) para Team Mikata.*
> *Fecha: 16 de febrero de 2026*
> *"Un agente no es un chatbot con más pasos. Es una entidad que percibe, decide, actúa, y aprende."*
