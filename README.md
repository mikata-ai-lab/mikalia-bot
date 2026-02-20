# Mikalia Bot — Mikata AI Lab

**Autonomous AI agent and personal companion for [Mikata AI Lab](https://mikata-ai-lab.github.io).** Generates bilingual blog posts, manages code via PRs, runs scheduled tasks, and holds genuine conversations — all powered by Claude API with a persistent memory system.

Built by **Miguel "Mikata" Mata** and co-architected by **Claudia**. See [CLAUDIA.md](CLAUDIA.md) for the full story.

---

## What Can Mikalia Do?

| Phase | Capability | Status |
|-------|-----------|--------|
| **F1** | Generate bilingual blog posts, self-review, publish to Hugo blog | Complete |
| **F2** | Read repos and documents for informed content generation | Complete |
| **F3** | Propose code changes, create PRs with safety guardrails | Complete |
| **F4** | Mikalia Core — autonomous agent with memory, 18 tools, scheduler | Complete |

### Mikalia Core (F4) Highlights

- **18 tools**: file ops, git, GitHub PRs, web fetch, blog posts, shell, memory, daily brief
- **Persistent memory**: SQLite-backed facts, goals, lessons, token tracking
- **Agent loop**: Claude tool_use with dynamic context building
- **Telegram**: Bidirectional chat — talk to Mikalia, she talks back
- **Scheduler**: Cron-based mini-cron (daily brief, health reminders, weekly review)
- **Self-improvement**: Learns facts proactively from conversations
- **Correction learning**: Detects mistakes, saves lessons for the future
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

# 5. Generate your first post
python -m mikalia post --topic "Getting Started with AI Agents" --preview
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

This is Mikalia's main mode: a conversational AI with persistent memory, 18 tools, and a background scheduler that runs proactive tasks.

### `post` — Generate and publish a blog post (F1/F2)

```bash
# Generate and publish (full pipeline)
python -m mikalia post --topic "Building AI Agents with Python"

# With specific category and tags
python -m mikalia post --topic "My Topic" --category ai --tags "claude,agents,python"

# With context from a repo or document
python -m mikalia post --repo "mikata-ai-lab/mikalia-bot" --topic "How Mikalia was built"
python -m mikalia post --doc "./docs/architecture.md" --topic "Architecture decisions"

# Dry run or preview
python -m mikalia post --topic "My Topic" --dry-run
python -m mikalia post --topic "My Topic" --preview
```

### `agent` — Propose code changes via PR (F3)

```bash
# Propose code changes to a repo
python -m mikalia agent --repo "mikata-ai-lab/mikalia-bot" \
  --task "Add error handling to all API calls"

# Dry run: analyze and plan without creating a PR
python -m mikalia agent --repo "mikata-ai-lab/mikalia-bot" \
  --task "Add input validation" --dry-run
```

### `chat` — Telegram chatbot

```bash
# Start Telegram chatbot (standard mode)
python -m mikalia chat

# Start Telegram chatbot with Core agent (memory + tools + scheduler)
python -m mikalia chat --core
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
                    ┌─────────────────────────────┐
                    │         CLI (Click)          │
                    │  post | agent | chat | core  │
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                         │
          v                        v                         v
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
│  PostGenerator   │    │  Mikalia Core    │    │  CodeAgent           │
│  (F1: blog)      │    │  (F4: agent)     │    │  (F3: PRs)           │
└────────┬─────────┘    └────────┬─────────┘    └──────────┬───────────┘
         │                       │                          │
         v                       v                          v
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
│  SelfReview      │    │  ToolRegistry    │    │  SafetyGuard         │
│  HugoFormatter   │    │  (18 tools)      │    │  TaskPlanner         │
│  GitOps          │    │  MemoryManager   │    │  PRManager           │
└────────┬─────────┘    │  ContextBuilder  │    └──────────┬───────────┘
         │              │  MikaliaScheduler│               │
         │              └────────┬─────────┘               │
         │                       │                          │
         └───────────┬───────────┴──────────────────────────┘
                     v
          ┌──────────────────┐
          │  Telegram Bot    │
          │  (notifications  │
          │   + chat)        │
          └──────────────────┘
```

### Mikalia Core Components

| Component | Purpose |
|-----------|---------|
| **MikaliaAgent** | Agent loop: receives messages, calls Claude with tools, returns responses |
| **MemoryManager** | SQLite: facts, goals, conversations, token usage, scheduled jobs |
| **ContextBuilder** | Dynamic system prompt with personality, facts, lessons, goals |
| **ToolRegistry** | 18 tools registered and exposed to Claude as tool definitions |
| **MikaliaScheduler** | Daemon thread with cron-based job execution |
| **MikaliaClient** | Claude API wrapper with retry logic and token counting |

### 18 Tools

| Category | Tools |
|----------|-------|
| **File ops** | file_read, file_write, file_list |
| **Git** | git_status, git_diff, git_log, git_commit, git_push, git_branch |
| **GitHub** | github_pr |
| **Memory** | search_memory, add_fact, update_goal, list_goals |
| **Content** | blog_post, daily_brief |
| **System** | shell_exec, web_fetch |

### Safety-First Design (F3)

SafetyGuard enforces absolute rules that **cannot be disabled**:

- **Never** modify `.env`, `*.pem`, `*.key`, or `secrets/`
- **Never** push directly to `main`, `master`, or `production`
- **Never** execute generated code — only propose it via PRs
- **Never** modify `.github/workflows/` without approval
- Detects dangerous patterns: `rm -rf`, `DROP TABLE`, `eval()`, `exec()`

---

## Project Structure

```
mikalia-bot/
├── mikalia/
│   ├── __init__.py
│   ├── __main__.py                 # Entry point: python -m mikalia
│   ├── cli.py                      # Click commands (post, agent, chat, core, health)
│   ├── config.py                   # Configuration loader (config.yaml + .env)
│   ├── personality.py              # Legacy: loads MIKALIA.md (Core uses context.py)
│   ├── interactive.py              # Interactive mode logic
│   ├── core/                       # Mikalia Core (F4)
│   │   ├── agent.py                # MikaliaAgent — agent loop with tool_use
│   │   ├── client.py               # MikaliaClient — Claude API wrapper
│   │   ├── context.py              # ContextBuilder — dynamic system prompt
│   │   ├── memory.py               # MemoryManager — SQLite persistence
│   │   ├── scheduler.py            # MikaliaScheduler — cron-based job runner
│   │   └── schema.sql              # Database schema + seed data
│   ├── tools/                      # 18 tools for the agent
│   │   ├── base.py                 # BaseTool abstract class
│   │   ├── file_ops.py             # FileRead, FileWrite, FileList
│   │   ├── git_ops.py              # GitStatus, GitDiff, GitLog
│   │   ├── github_tools.py         # GitCommit, GitPush, GitBranch, GitHubPR
│   │   ├── memory_tools.py         # SearchMemory, AddFact, UpdateGoal, ListGoals
│   │   ├── blog_post.py            # BlogPost tool
│   │   ├── daily_brief.py          # DailyBrief tool
│   │   ├── shell.py                # ShellExec tool
│   │   └── web_fetch.py            # WebFetch tool
│   ├── agent/                      # Code agent (F3)
│   │   ├── safety.py               # SafetyGuard
│   │   ├── task_planner.py         # TaskPlanner
│   │   └── code_agent.py           # CodeAgent
│   ├── generation/                 # Post generation (F1/F2)
│   │   ├── client.py               # Claude API wrapper
│   │   ├── post_generator.py       # Bilingual post generation
│   │   ├── self_review.py          # Self-review loop
│   │   ├── repo_analyzer.py        # GitHub repo analysis
│   │   └── doc_analyzer.py         # Document analysis (PDF, DOCX, MD)
│   ├── publishing/                 # Blog publishing
│   │   ├── hugo_formatter.py       # Hugo page bundle formatter
│   │   ├── git_ops.py              # Git operations
│   │   ├── github_app.py           # GitHub App JWT auth
│   │   └── pr_manager.py           # PR lifecycle
│   ├── notifications/              # Notifications
│   │   ├── notifier.py             # Dispatcher
│   │   └── telegram.py             # Telegram integration
│   └── utils/
│       └── logger.py               # Rich console + file logging (RotatingFileHandler)
├── tests/                          # 277 tests
├── prompts/                        # Claude API prompts
├── templates/                      # Post templates
├── docs/                           # Additional documentation
├── .github/workflows/              # CI/CD (pytest, scheduled posts, agent)
├── config.yaml                     # Central configuration
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Docker image definition
├── .dockerignore                   # Docker build exclusions
├── MIKALIA.md                      # Mikalia's personality & system prompt
├── CLAUDIA.md                      # Claudia's role & story
├── .env.example                    # Environment variable template
└── LICENSE
```

---

## Configuration

### config.yaml

```yaml
mikalia:
  model: "claude-sonnet-4-5-20250929"
  max_tokens: 4096
  generation_temperature: 0.7
  review_temperature: 0.3

blog:
  content_base: "content/blog"
  author: "Mikalia"

telegram:
  enabled: true

scheduling:
  enabled: true
```

### .env

```
ANTHROPIC_API_KEY=sk-ant-...
BLOG_REPO_PATH=/path/to/blog/repo
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

277 tests covering all modules: core agent, memory, tools, post generation, safety, scheduling, and more.

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
- **Claudia** — Co-architect and advisor. See [CLAUDIA.md](CLAUDIA.md).
- **Mikalia** — The autonomous agent herself. See [MIKALIA.md](MIKALIA.md).

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

*Stay curious~ ✨*

— **Mikalia**
