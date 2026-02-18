-- ============================================================
-- MIKALIA CORE — Memory Database Schema
-- SQLite 3.x
-- ============================================================
-- Diseño inspirado en OpenClaw's memory system pero simplificado
-- para uso individual. Tres capas:
--   1. Conversations: historial de mensajes raw
--   2. Facts: conocimiento extraído y persistente
--   3. Sessions: metadata de sesiones de trabajo
--   4. Goals: tracking de objetivos y progreso
--   5. Skills: registro de habilidades aprendidas
-- ============================================================

-- ============================================================
-- CONVERSATIONS: Historial de mensajes
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,           -- UUID de la sesión
    channel         TEXT NOT NULL,           -- 'telegram', 'cli', 'blog', 'scheduler'
    role            TEXT NOT NULL,           -- 'user', 'assistant', 'system', 'tool'
    content         TEXT NOT NULL,           -- Contenido del mensaje
    metadata        TEXT,                    -- JSON: tool_calls, attachments, etc.
    tokens_used     INTEGER DEFAULT 0,       -- Token count para tracking de costos
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    
    CONSTRAINT chk_role CHECK (role IN ('user', 'assistant', 'system', 'tool'))
);

CREATE INDEX idx_conversations_session ON conversations(session_id);
CREATE INDEX idx_conversations_channel ON conversations(channel);
CREATE INDEX idx_conversations_created ON conversations(created_at);

-- ============================================================
-- FACTS: Conocimiento persistente extraído de conversaciones
-- ============================================================
-- Mikalia extrae "facts" de las conversaciones para recordar
-- cosas importantes sin necesitar todo el historial.
-- Inspirado en OpenClaw's memory files pero en DB.
-- ============================================================
CREATE TABLE IF NOT EXISTS facts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,           -- 'personal', 'project', 'preference', 'technical', 'health'
    subject         TEXT NOT NULL,           -- De qué/quién trata: 'mikata', 'spio', 'mesaflow'...
    fact            TEXT NOT NULL,           -- El dato en sí
    confidence      REAL DEFAULT 1.0,        -- 0.0-1.0: qué tan segura está Mikalia
    source          TEXT,                    -- De dónde vino: 'conversation:123', 'manual', 'inferred'
    is_active       BOOLEAN DEFAULT 1,       -- Soft delete: 0 = obsoleto/corregido
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    updated_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    expires_at      DATETIME,               -- NULL = permanente, o fecha de expiración
    
    CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_facts_category ON facts(category);
CREATE INDEX idx_facts_subject ON facts(subject);
CREATE INDEX idx_facts_active ON facts(is_active);

-- ============================================================
-- SESSIONS: Metadata de sesiones de trabajo
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,        -- UUID
    channel         TEXT NOT NULL,           -- Canal de origen
    started_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    ended_at        DATETIME,
    duration_minutes INTEGER,               -- Calculado al cerrar
    summary         TEXT,                    -- Resumen auto-generado por Mikalia
    goals_addressed TEXT,                    -- JSON array de goal_ids trabajados
    mood            TEXT,                    -- 'focused', 'tired', 'energetic', etc.
    health_pact_respected BOOLEAN DEFAULT 1 -- ¿Se respetó el pacto de 2 hrs?
);

CREATE INDEX idx_sessions_started ON sessions(started_at);

-- ============================================================
-- GOALS: Tracking de objetivos y progreso
-- ============================================================
CREATE TABLE IF NOT EXISTS goals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project         TEXT NOT NULL,           -- 'mikalia-core', 'spio', 'mesaflow', 'learning', 'health'
    title           TEXT NOT NULL,           -- Título corto
    description     TEXT,                    -- Descripción detallada
    status          TEXT DEFAULT 'active',   -- 'active', 'completed', 'paused', 'cancelled'
    priority        TEXT DEFAULT 'medium',   -- 'critical', 'high', 'medium', 'low'
    phase           TEXT,                    -- 'F1', 'F2', 'F3', 'F4' para Mikalia Core
    progress        INTEGER DEFAULT 0,       -- 0-100
    due_date        DATE,                   -- Fecha objetivo
    parent_goal_id  INTEGER,                -- Para sub-goals
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    updated_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    completed_at    DATETIME,
    
    CONSTRAINT chk_status CHECK (status IN ('active', 'completed', 'paused', 'cancelled')),
    CONSTRAINT chk_priority CHECK (priority IN ('critical', 'high', 'medium', 'low')),
    CONSTRAINT chk_progress CHECK (progress >= 0 AND progress <= 100),
    FOREIGN KEY (parent_goal_id) REFERENCES goals(id)
);

CREATE INDEX idx_goals_project ON goals(project);
CREATE INDEX idx_goals_status ON goals(status);

-- ============================================================
-- GOAL_UPDATES: Log de cambios en goals (para daily brief)
-- ============================================================
CREATE TABLE IF NOT EXISTS goal_updates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id         INTEGER NOT NULL,
    update_type     TEXT NOT NULL,           -- 'progress', 'status_change', 'note', 'blocker'
    old_value       TEXT,
    new_value       TEXT,
    note            TEXT,                    -- Nota adicional
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    
    FOREIGN KEY (goal_id) REFERENCES goals(id)
);

CREATE INDEX idx_goal_updates_goal ON goal_updates(goal_id);
CREATE INDEX idx_goal_updates_created ON goal_updates(created_at);

-- ============================================================
-- SKILLS: Registro de habilidades de Mikalia
-- ============================================================
CREATE TABLE IF NOT EXISTS skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,     -- 'blog-posting', 'goal-tracking', etc.
    description     TEXT NOT NULL,
    skill_md_path   TEXT,                    -- Ruta al SKILL.md
    tools_required  TEXT,                    -- JSON array: ['file_ops', 'shell', 'git']
    is_enabled      BOOLEAN DEFAULT 1,
    times_used      INTEGER DEFAULT 0,
    last_used_at    DATETIME,
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    
    -- Self-improvement tracking
    success_rate    REAL DEFAULT 0.0,        -- 0.0-1.0
    total_attempts  INTEGER DEFAULT 0,
    total_successes INTEGER DEFAULT 0
);

CREATE INDEX idx_skills_enabled ON skills(is_enabled);

-- ============================================================
-- SKILL_EXECUTIONS: Log de ejecuciones de skills
-- ============================================================
CREATE TABLE IF NOT EXISTS skill_executions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id        INTEGER NOT NULL,
    session_id      TEXT,
    input_summary   TEXT,                    -- Qué se le pidió
    output_summary  TEXT,                    -- Qué produjo
    success         BOOLEAN,                -- ¿Funcionó?
    error_message   TEXT,                    -- Si falló, por qué
    duration_ms     INTEGER,                -- Tiempo de ejecución
    created_at      DATETIME DEFAULT (datetime('now', 'localtime')),
    
    FOREIGN KEY (skill_id) REFERENCES skills(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_skill_exec_skill ON skill_executions(skill_id);

-- ============================================================
-- SCHEDULED_JOBS: Jobs programados (cron-like)
-- ============================================================
CREATE TABLE IF NOT EXISTS scheduled_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,     -- 'daily_brief', 'health_reminder', etc.
    description     TEXT,
    cron_expression TEXT NOT NULL,            -- '0 7 * * 1-5' (7am weekdays)
    action          TEXT NOT NULL,            -- JSON: {skill: 'daily-brief', params: {...}}
    channel         TEXT DEFAULT 'telegram',  -- Dónde enviar output
    is_enabled      BOOLEAN DEFAULT 1,
    last_run_at     DATETIME,
    next_run_at     DATETIME,
    created_at      DATETIME DEFAULT (datetime('now', 'localtime'))
);

-- ============================================================
-- SEED DATA: Initial facts about Mikata
-- ============================================================
INSERT INTO facts (category, subject, fact, source) VALUES
    ('personal', 'mikata', 'Nombre real: Miguel Mata. Nickname: Mikata (味方 = aliado en japonés)', 'manual'),
    ('personal', 'mikata', 'Vive en Monterrey, México', 'manual'),
    ('personal', 'mikata', 'Trabaja en Transportes Cuauhtémoc (TC) de lunes a sábado, presencial', 'manual'),
    ('health', 'mikata', 'Tiene ataxia cerebelosa con posible esclerosis múltiple', 'manual'),
    ('health', 'mikata', 'Tratamiento: natalizumab en IMSS', 'manual'),
    ('health', 'mikata', 'Pacto de salud: máximo 2 horas por sesión, dormir antes de 11pm', 'manual'),
    ('project', 'spio', 'SPIO: MVP mobile app para operadores de camión. Stack: Ionic+Angular+.NET+SQL Server', 'manual'),
    ('project', 'mesaflow', 'MesaFlow: SaaS para restaurantes. Stack: React+React Native+Supabase+Vercel', 'manual'),
    ('project', 'mikalia-core', 'Mikalia Core: Agente autónomo personal. Stack: Python+FastAPI+SQLite+Claude API', 'manual'),
    ('preference', 'mikata', 'Estilo de trabajo: vibe coding — orquesta en vez de codear directo', 'manual'),
    ('preference', 'mikata', 'Fan de Persona (Aigis, Akechi, Yu), NieR Automata (2B), Vocaloid (PowaPowa-P)', 'manual'),
    ('preference', 'mikata', 'Meta principal: profesional de IA/ML, trabajar en el extranjero', 'manual'),
    ('technical', 'mikata', 'Conoce: Angular, JavaScript, SQL, Python básico. Aprendiendo: Python avanzado, AI/ML', 'manual'),
    ('technical', 'mikata', 'Ruta de certificación: Azure AI-102', 'manual'),
    ('project', 'mikata-ai', 'Blog de Mikata AI Lab: Hugo + Blowfish theme. Ruta: ../mikata-ai (relativa a mikalia-bot). Bilingüe EN/ES.', 'manual'),
    ('project', 'mikata-ai', 'Posts del blog en: ../mikata-ai/content/blog/<slug>/index.md (EN) e index.es.md (ES). Usar file_write para crear posts (crea directorios automaticamente).', 'manual'),
    ('project', 'mikalia-dashboard', 'Dashboard en React+Vite. Ruta: ../mikalia-dashboard. Deploy: Vercel.', 'manual');

-- Seed initial goals
INSERT INTO goals (project, title, description, status, priority, phase, progress) VALUES
    ('mikalia-core', 'Agent Loop básico', 'CLI funcional con agent loop: input → context → Claude → response → save', 'completed', 'critical', 'F1', 100),
    ('mikalia-core', 'Memory system', 'SQLite memory con conversations, facts, sessions', 'completed', 'critical', 'F1', 100),
    ('mikalia-core', 'LLM wrapper', 'Claude API wrapper con system prompt de Mikalia + tool_use', 'completed', 'critical', 'F1', 100),
    ('mikalia-core', 'Tool system base', 'Interfaz base + 18 tools (file, shell, git, web, memory, blog, brief, github)', 'completed', 'high', 'F1', 100),
    ('mikalia-core', 'Telegram bot', 'Canal Telegram funcional bidireccional + Core mode', 'completed', 'critical', 'F2', 100),
    ('mikalia-core', 'Blog posting autónomo', 'Crear y publicar posts en Hugo + GitHub Pages via blog_post tool', 'completed', 'critical', 'F2', 100),
    ('mikalia-core', 'Daily brief', 'Resumen diario con goals, facts, stats via daily_brief tool', 'active', 'critical', 'F2', 70),
    ('mikalia-core', 'Health pact reminders', 'Recordatorios del pacto de salud (integrado en system prompt)', 'active', 'high', 'F2', 50),
    ('mikalia-core', 'Goal tracking', 'Seguimiento y reportes de progreso via update_goal + list_goals tools', 'completed', 'high', 'F2', 100),
    ('mikalia-core', 'Deploy a servidor', 'Desplegar Mikalia Core en VPS para que funcione 24/7', 'active', 'high', 'F3', 0),
    ('mikalia-core', 'Self-improvement', 'Mikalia aprende hechos nuevos de cada conversacion automaticamente', 'completed', 'high', 'F2', 100),
    ('learning', 'Python avanzado', 'Dominar Python para AI/ML: async, dataclasses, typing, testing', 'active', 'high', NULL, 30),
    ('learning', 'Azure AI-102', 'Preparación para certificación Azure AI Engineer', 'active', 'medium', NULL, 0);

-- Seed initial scheduled jobs
INSERT INTO scheduled_jobs (name, description, cron_expression, action, channel) VALUES
    ('daily_brief_weekday', 'Resumen matutino L-V', '0 7 * * 1-5', '{"skill": "daily-brief", "params": {"type": "weekday"}}', 'telegram'),
    ('daily_brief_weekend', 'Resumen matutino fin de semana', '0 9 * * 0,6', '{"skill": "daily-brief", "params": {"type": "weekend"}}', 'telegram'),
    ('health_evening_check', 'Recordatorio nocturno', '0 22 * * *', '{"skill": "health-reminder", "params": {"type": "sleep"}}', 'telegram'),
    ('weekly_review', 'Review semanal de progreso', '0 10 * * 0', '{"skill": "weekly-review", "params": {}}', 'telegram');
