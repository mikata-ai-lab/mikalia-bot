# Mikalia Bot — Mikata AI Lab

**Autonomous AI agent for [Mikata AI Lab](https://mikata-ai-lab.github.io).** Generates bilingual blog posts, reads repos and documents for context, and proposes code changes via pull requests — all with safety-first architecture.

Built with Claude API, Python 3.11+, and a safety-first philosophy: Mikalia never touches secrets, never pushes to main, and never executes generated code.

---

## What Can Mikalia Do?

| Phase | Capability | Status |
|-------|-----------|--------|
| **F1** | Generate bilingual blog posts, self-review, publish to Hugo blog | Complete |
| **F2** | Read repos and documents for informed content generation | Complete |
| **F3** | Propose code changes, create PRs with safety guardrails | Complete |

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

---

## Commands

### `post` — Generate and publish a blog post (F1)

```bash
# Generate and publish (full pipeline)
python -m mikalia post --topic "Building AI Agents with Python"

# With specific category and tags
python -m mikalia post --topic "My Topic" --category ai --tags "claude,agents,python"

# Dry run: generate and save locally, do not push
python -m mikalia post --topic "My Topic" --dry-run

# Preview: display in terminal only, do not save or push
python -m mikalia post --topic "My Topic" --preview
```

### `post` with context — Informed posts from repos and docs (F2)

```bash
# Generate post based on a repo
python -m mikalia post --repo "mikata-ai-lab/mikalia-bot" \
  --topic "How Mikalia Bot was built"

# Generate post based on a local document
python -m mikalia post --doc "./docs/architecture.md" \
  --topic "Architecture decisions in Mikalia"

# Combine repo + topic
python -m mikalia post --repo "anthropics/anthropic-sdk-python" \
  --topic "Understanding the Anthropic Python SDK"
```

### `agent` — Propose code changes via PR (F3)

```bash
# Propose code changes to a repo
python -m mikalia agent --repo "mikata-ai-lab/mikalia-bot" \
  --task "Add error handling to all API calls"

# Fix a bug
python -m mikalia agent --repo "mikata-ai-lab/mikalia-bot" \
  --task "Fix: Telegram notification fails when post title has emojis"

# Dry run: analyze and plan without creating a PR
python -m mikalia agent --repo "mikata-ai-lab/mikalia-bot" \
  --task "Add input validation" --dry-run
```

### `interactive` — Guided post creation

```bash
python -m mikalia interactive
```

### `config` — View and validate configuration

```bash
python -m mikalia config --show       # Show current configuration
python -m mikalia config --validate   # Validate required settings
```

### `health` — Check all connections

```bash
python -m mikalia health
```

---

## Architecture

```
                         ┌──────────────────────┐
                         │     CLI (Click)       │
                         │  post | agent | ...   │
                         └──────────┬───────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                   │
                 v                  v                   v
     ┌───────────────────┐  ┌─────────────┐  ┌─────────────────┐
     │  PostGenerator    │  │  CodeAgent  │  │  RepoAnalyzer   │
     │  (F1: blog posts) │  │  (F3: PRs)  │  │  DocAnalyzer    │
     └────────┬──────────┘  └──────┬──────┘  │  (F2: context)  │
              │                    │          └─────────────────┘
              v                    v
     ┌────────────────┐   ┌───────────────┐
     │  SelfReview    │   │  TaskPlanner  │
     │  (quality)     │   │  (planning)   │
     └────────┬───────┘   └───────┬───────┘
              │                   │
              v                   v
     ┌────────────────┐   ┌───────────────┐
     │  HugoFormatter │   │  SafetyGuard  │  <-- SACRED: never bypassed
     │  + GitOps      │   │  (guardrails) │
     └────────┬───────┘   └───────┬───────┘
              │                   │
              v                   v
     ┌────────────────┐   ┌───────────────┐
     │  Blog Repo     │   │  PRManager    │
     │  (direct push) │   │  (branches +  │
     └────────┬───────┘   │   PRs via gh) │
              │           └───────┬───────┘
              └─────────┬─────────┘
                        v
              ┌───────────────────┐
              │  Notifier         │
              │  (Telegram)       │
              └───────────────────┘
```

### Safety-First Design (F3)

SafetyGuard enforces absolute rules that **cannot be disabled**:

- **Never** modify `.env`, `*.pem`, `*.key`, or `secrets/`
- **Never** push directly to `main`, `master`, or `production`
- **Never** execute generated code — only propose it via PRs
- **Never** modify `.github/workflows/` without approval
- **Never** force push or delete protected branches
- Detects dangerous patterns: `rm -rf`, `DROP TABLE`, `eval()`, `exec()`
- Configurable limits: max files per PR, max lines changed, allowed extensions

---

## Project Structure

```
mikalia-bot/
├── mikalia/
│   ├── __init__.py
│   ├── __main__.py                 # Entry point: python -m mikalia
│   ├── cli.py                      # Click commands (post, agent, interactive, config, health)
│   ├── config.py                   # Configuration loader (config.yaml + .env)
│   ├── personality.py              # Loads MIKALIA.md system prompt
│   ├── interactive.py              # Interactive mode logic
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── safety.py               # SafetyGuard — absolute rules + configurable limits
│   │   ├── task_planner.py         # TaskPlanner — classify, decompose, estimate
│   │   └── code_agent.py           # CodeAgent — full analyze-plan-generate-validate flow
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── client.py               # Claude API wrapper (MikaliaClient)
│   │   ├── post_generator.py       # Orchestrates bilingual post generation
│   │   ├── self_review.py          # Self-review loop (7 criteria, max 2 iterations)
│   │   ├── repo_analyzer.py        # Clones/analyzes GitHub repos for context
│   │   └── doc_analyzer.py         # Reads .md, .pdf, .docx, .yaml, .json for context
│   ├── publishing/
│   │   ├── __init__.py
│   │   ├── hugo_formatter.py       # Formats posts as Hugo page bundles
│   │   ├── git_ops.py              # Git commit, push, sync operations
│   │   ├── github_app.py           # GitHub App JWT authentication
│   │   └── pr_manager.py           # Branch, commit, push, PR lifecycle via gh CLI
│   ├── notifications/
│   │   ├── __init__.py
│   │   ├── notifier.py             # Notification dispatcher
│   │   └── telegram.py             # Telegram channel implementation
│   └── utils/
│       ├── __init__.py
│       └── logger.py               # Rich-powered logging (UTF-8 safe on Windows)
├── tests/                          # 93 tests covering all modules
│   ├── test_config.py
│   ├── test_generator.py
│   ├── test_hugo_formatter.py
│   ├── test_self_review.py
│   ├── test_repo_analyzer.py
│   ├── test_doc_analyzer.py
│   ├── test_safety.py
│   └── test_task_planner.py
├── prompts/                        # Claude API prompts
│   ├── post_generation.md
│   ├── post_review.md
│   ├── repo_analysis.md
│   ├── doc_analysis.md
│   ├── code_changes.md
│   └── pr_description.md
├── templates/                      # Post templates
├── docs/                           # Additional documentation
├── .github/
│   └── workflows/
│       ├── test.yml                # CI pipeline (pytest on push)
│       ├── scheduled_post.yml      # Cron: Mon/Thu 16:00 UTC
│       └── mikalia_agent.yml       # Manual trigger for code agent
├── config.yaml                     # Central configuration
├── requirements.txt                # Python dependencies
├── MIKALIA.md                      # Mikalia's personality prompt
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
  max_review_iterations: 2

blog:
  content_base: "content/blog"
  en_filename: "index.md"
  es_filename: "index.es.md"
  author: "Mikalia"

git:
  default_branch: "main"

repos:
  cache_dir: "~/.mikalia/repos"
  allowed:
    - "mikata-ai-lab/*"
  cache_ttl_days: 7

scheduling:
  enabled: true
  cron: "0 16 * * 1,4"   # Mon/Thu 16:00 UTC (10:00 CST)

telegram:
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

## Branch Naming Convention (F3)

```
mikalia/post/{slug}     — new blog post
mikalia/fix/{slug}      — bug fix
mikalia/feat/{slug}     — new feature
mikalia/docs/{slug}     — documentation
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

93 tests covering configuration, post generation, Hugo formatting, self-review, repo analysis, document analysis, safety guardrails, and task planning.

---

## GitHub Actions

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `test.yml` | Push to main | Run pytest CI |
| `scheduled_post.yml` | Cron (Mon/Thu) or manual | Auto-generate blog posts |
| `mikalia_agent.yml` | Manual dispatch | Run code agent on a repo |

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Credits

Created by **Miguel "Mikata" Mata** at [Mikata AI Lab](https://mikata-ai-lab.github.io).

Powered by the [Claude API](https://docs.anthropic.com/en/docs/welcome) from Anthropic.
