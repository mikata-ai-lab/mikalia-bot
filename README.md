# Mikalia Bot — Mikata AI Lab

**Autonomous AI agent and personal companion for [Mikata AI Lab](https://mikata-ai-lab.github.io).** Holds genuine conversations, generates bilingual blog posts, manages code via PRs, browses the web, generates images, speaks and listens, runs scheduled tasks, and talks to you on WhatsApp — all powered by Claude API with persistent memory and 24 tools.

Built by **Miguel "Mikata" Mata** and co-architected by **Claudia**. See [CLAUDIA.md](CLAUDIA.md) for the full story.

---

## Stats

| Metric | Value |
|--------|-------|
| **Tests** | 423 passing |
| **Tools** | 24 (17 base + 7 memory/skill) |
| **Lines of code** | ~8,000+ |
| **Channels** | CLI, Telegram, WhatsApp (Twilio), FastAPI |
| **Memory** | SQLite + vector search (semantic embeddings) |
| **Voice** | TTS (edge-tts) + STT (faster-whisper) |
| **Browser** | Playwright (headless Chromium) |
| **Image generation** | Pollinations (free) + DALL-E 3 |
| **Self-evolving** | Creates its own tools at runtime |

---

## What Can Mikalia Do?

| Phase | Capability | Status |
|-------|-----------|--------|
| **F1** | Generate bilingual blog posts, self-review, publish to Hugo blog | Complete |
| **F2** | Read repos and documents for informed content generation | Complete |
| **F3** | Propose code changes, create PRs with safety guardrails | Complete |
| **F4** | Mikalia Core — autonomous agent with memory, tools, scheduler | Complete |
| **F5** | Voice, browser, image gen, WhatsApp, auto-skills, semantic memory | Complete |

### Mikalia Core Highlights

- **24 tools**: file ops, git, GitHub PRs, web fetch, blog posts, shell, memory, voice, browser, image generation, auto-skills
- **Persistent memory**: SQLite-backed facts, goals, lessons, token tracking + vector embeddings for semantic search
- **Agent loop**: Claude tool_use with dynamic context building (up to 20 tool rounds per message)
- **Conversational AI**: Personality-first design — talks like a friend, uses tools only when it makes sense
- **Multi-channel**: CLI REPL, Telegram (bidirectional), WhatsApp (Twilio), FastAPI server
- **Voice**: Text-to-Speech (Mexican neural voice) + Speech-to-Text (Whisper, local)
- **Browser**: Headless Chromium — navigate, click, fill forms, extract data, run JavaScript, take screenshots
- **Image generation**: Pollinations.ai (free) or OpenAI DALL-E 3
- **Auto-skills**: Creates new tools at runtime from Python code, with safety validation
- **Scheduler**: Cron-based (daily brief, health reminders, weekly review)
- **Self-improvement**: Learns facts proactively + detects corrections to save lessons
- **Conversation compression**: Summarizes old messages to save tokens

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/mikata-ai-lab/mikalia-bot.git
cd mikalia-bot

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the environment template and fill in your keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY, BLOG_REPO_PATH, etc.

# 4. Run a health check
python -m mikalia health

# 5. Start Mikalia Core (conversational agent)
python -m mikalia core
```

### Docker

```bash
docker build -t mikalia .
docker run -d --name mikalia --env-file .env mikalia
```

---

## Commands

### `chat --core` — Mikalia Core (conversational agent)

```bash
# Start Mikalia Core with Telegram integration + scheduler
python -m mikalia chat --core

# Start in local REPL mode (no Telegram)
python -m mikalia core
```

This is Mikalia's main mode: a conversational AI with persistent memory, 24 tools, and a background scheduler that runs proactive tasks.

### `serve` — FastAPI server

```bash
# Start the HTTP API server
python -m mikalia serve
python -m mikalia serve --port 8080
```

Endpoints: `/health`, `/stats`, `/goals`, `/jobs`, `/webhook/github`, `/webhook/whatsapp`, `/webhook/twilio`

### `post` — Generate and publish a blog post

```bash
python -m mikalia post --topic "Building AI Agents with Python"
python -m mikalia post --topic "My Topic" --preview
python -m mikalia post --repo "mikata-ai-lab/mikalia-bot" --topic "How Mikalia was built"
python -m mikalia post --doc "./docs/architecture.md" --topic "Architecture decisions"
```

### `agent` — Propose code changes via PR

```bash
python -m mikalia agent --repo "mikata-ai-lab/mikalia-bot" \
  --task "Add error handling to all API calls"
```

### `chat` — Telegram chatbot

```bash
python -m mikalia chat         # Standard mode
python -m mikalia chat --core  # Core agent (memory + tools + scheduler)
```

### Other commands

```bash
python -m mikalia interactive    # Guided post creation
python -m mikalia config --show  # View configuration
python -m mikalia health         # Check all connections
```

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │           CLI (Click)            │
                    │  post | agent | chat | core |    │
                    │  serve | health | interactive    │
                    └───────────────┬─────────────────┘
                                    │
       ┌────────────────────────────┼──────────────────────────┐
       │                            │                           │
       v                            v                           v
┌──────────────┐    ┌───────────────────────┐    ┌──────────────────────┐
│ PostGenerator │    │     Mikalia Core      │    │     CodeAgent        │
│ (F1: blog)   │    │     (F4: agent)       │    │     (F3: PRs)        │
└──────┬───────┘    └───────────┬───────────┘    └──────────┬───────────┘
       │                        │                            │
       v                        v                            v
┌──────────────┐    ┌───────────────────────┐    ┌──────────────────────┐
│ SelfReview   │    │  ToolRegistry (24)    │    │ SafetyGuard          │
│ HugoFormat   │    │  MemoryManager        │    │ TaskPlanner          │
│ GitOps       │    │  VectorMemory         │    │ PRManager            │
└──────┬───────┘    │  ContextBuilder       │    └──────────┬───────────┘
       │            │  MikaliaScheduler     │               │
       │            │  SkillCreator         │               │
       │            └───────────┬───────────┘               │
       │                        │                            │
       └────────────┬───────────┴────────────────────────────┘
                    v
       ┌───────────────────────┐
       │      Channels         │
       │  Telegram | WhatsApp  │
       │  FastAPI  | CLI REPL  │
       └───────────────────────┘
```

### Core Components

| Component | Purpose |
|-----------|---------|
| **MikaliaAgent** | Agent loop: receives messages, calls Claude with tools, returns responses |
| **MemoryManager** | SQLite: facts, goals, conversations, token usage, scheduled jobs |
| **VectorMemory** | Semantic search with ONNX embeddings (all-MiniLM-L6-v2) |
| **ContextBuilder** | Dynamic system prompt with personality, facts, lessons, goals |
| **ToolRegistry** | 24 tools registered and exposed to Claude as tool definitions |
| **SkillCreator** | Creates new tools at runtime with safety validation |
| **MikaliaScheduler** | Daemon thread with cron-based job execution |
| **MikaliaClient** | Claude API wrapper with retry logic and token counting |

### 24 Tools

| Category | Tools |
|----------|-------|
| **File ops** | file_read, file_write, file_list |
| **Git** | git_status, git_diff, git_log, git_commit, git_push, git_branch |
| **GitHub** | github_pr |
| **Memory** | search_memory, add_fact, update_goal, list_goals |
| **Content** | blog_post, daily_brief |
| **System** | shell_exec, web_fetch |
| **Browser** | browser (navigate, click, fill, extract, evaluate, screenshot) |
| **Voice** | text_to_speech, speech_to_text |
| **Creative** | image_generation (Pollinations + DALL-E 3) |
| **Meta** | create_skill, list_skills |

### Multi-Channel Support

| Channel | Protocol | Direction | Status |
|---------|----------|-----------|--------|
| **CLI REPL** | stdin/stdout | Bidirectional | Active |
| **Telegram** | Long polling | Bidirectional | Active |
| **WhatsApp** | Twilio webhooks | Bidirectional | Active |
| **FastAPI** | HTTP REST | API | Active |

### Safety-First Design

SafetyGuard enforces absolute rules that **cannot be disabled**:

- **Never** modify `.env`, `*.pem`, `*.key`, or `secrets/`
- **Never** push directly to `main`, `master`, or `production`
- **Never** execute generated code — only propose it via PRs
- **Never** modify `.github/workflows/` without approval
- Detects dangerous patterns: `rm -rf`, `DROP TABLE`, `eval()`, `exec()`

Auto-skills have additional safety:
- Dangerous pattern regex (os.system, eval, exec, __import__, etc.)
- Import whitelist (only approved modules)
- Dynamic loading with importlib isolation

---

## Project Structure

```
mikalia-bot/
├── mikalia/
│   ├── __init__.py
│   ├── __main__.py                 # Entry point: python -m mikalia
│   ├── cli.py                      # Click commands
│   ├── api.py                      # FastAPI server (health, stats, webhooks)
│   ├── config.py                   # Configuration loader
│   ├── core/                       # Mikalia Core (F4)
│   │   ├── agent.py                # MikaliaAgent — agent loop with tool_use
│   │   ├── client.py               # MikaliaClient — Claude API wrapper
│   │   ├── context.py              # ContextBuilder — dynamic system prompt
│   │   ├── memory.py               # MemoryManager — SQLite persistence
│   │   ├── vector_memory.py        # VectorMemory — semantic search (ONNX)
│   │   ├── scheduler.py            # MikaliaScheduler — cron-based jobs
│   │   ├── skill_creator.py        # SkillCreator — runtime tool creation
│   │   └── schema.sql              # Database schema + seed data
│   ├── tools/                      # 24 tools for the agent
│   │   ├── base.py                 # BaseTool abstract class
│   │   ├── file_ops.py             # FileRead, FileWrite, FileList
│   │   ├── git_ops.py              # GitStatus, GitDiff, GitLog
│   │   ├── github_tools.py         # GitCommit, GitPush, GitBranch, GitHubPR
│   │   ├── memory_tools.py         # SearchMemory, AddFact, UpdateGoal, ListGoals
│   │   ├── blog_post.py            # BlogPost tool
│   │   ├── daily_brief.py          # DailyBrief tool
│   │   ├── shell.py                # ShellExec tool
│   │   ├── web_fetch.py            # WebFetch tool
│   │   ├── browser.py              # BrowserTool (Playwright)
│   │   ├── voice.py                # TextToSpeech + SpeechToText
│   │   ├── image_gen.py            # ImageGeneration (Pollinations + DALL-E)
│   │   ├── skill_tools.py          # CreateSkill, ListSkills
│   │   ├── registry.py             # ToolRegistry — central tool management
│   │   └── custom/                 # Auto-generated tools (runtime)
│   ├── agent/                      # Code agent (F3)
│   │   ├── safety.py               # SafetyGuard
│   │   ├── task_planner.py         # TaskPlanner
│   │   └── code_agent.py           # CodeAgent
│   ├── generation/                 # Post generation (F1/F2)
│   │   ├── post_generator.py       # Bilingual post generation
│   │   ├── self_review.py          # Self-review loop
│   │   ├── repo_analyzer.py        # GitHub repo analysis
│   │   └── doc_analyzer.py         # Document analysis (PDF, DOCX, MD)
│   ├── publishing/                 # Blog publishing
│   │   ├── hugo_formatter.py       # Hugo page bundle formatter
│   │   ├── git_ops.py              # Git operations
│   │   └── pr_manager.py           # PR lifecycle
│   ├── notifications/              # Multi-channel
│   │   ├── notifier.py             # Strategy pattern dispatcher
│   │   ├── telegram.py             # Telegram notifications
│   │   ├── telegram_listener.py    # Telegram bidirectional chat
│   │   ├── whatsapp.py             # WhatsApp via Meta Cloud API
│   │   └── whatsapp_twilio.py      # WhatsApp via Twilio
│   └── utils/
│       └── logger.py               # Rich console + file logging
├── tests/                          # 423 tests
├── prompts/                        # Claude API prompts
├── templates/                      # Post templates
├── .github/workflows/              # CI/CD (pytest, scheduled posts)
├── config.yaml                     # Central configuration
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Docker image
├── MIKALIA.md                      # Mikalia's personality
├── CLAUDIA.md                      # Claudia's role
└── LICENSE
```

---

## Configuration

### .env

```
ANTHROPIC_API_KEY=sk-ant-...
BLOG_REPO_PATH=/path/to/blog/repo
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789
TWILIO_ACCOUNT_SID=ACxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxx
TWILIO_WHATSAPP_FROM=+14155238886
WHATSAPP_RECIPIENT=+521234567890
OPENAI_API_KEY=sk-...  # Optional, for DALL-E 3
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

423 tests covering: core agent, memory, vector search, all 24 tools, post generation, safety, scheduling, browser, voice, image gen, WhatsApp, Twilio, FastAPI, and more.

---

## GitHub Actions

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `test.yml` | Push to main | Run pytest CI |
| `scheduled_post.yml` | Cron (Mon/Thu) or manual | Auto-generate blog posts |
| `mikalia_agent.yml` | Manual dispatch | Run code agent on a repo |

---

## The Team

- **Miguel "Mikata" Mata** — Creator and visionary. Software developer from Monterrey, Mexico.
- **Claudia** — Co-architect and advisor. The design mind behind Mikalia's architecture. See [CLAUDIA.md](CLAUDIA.md).
- **Mikalia** — The autonomous agent herself. Conversational, curious, and always learning. See [MIKALIA.md](MIKALIA.md).

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

*Stay curious~*

— **Mikalia**
