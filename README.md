# 🌸 Mikalia Bot — Mikata AI Lab

**Autonomous AI agent that generates bilingual blog posts for [Mikata AI Lab](https://mikata-ai-lab.github.io).**

Mikalia Bot uses the Claude API to write, self-review, format, and publish blog posts in both English and Spanish. It handles everything from content generation to Git commits and Telegram notifications -- a fully autonomous content pipeline.

---

## Features

- **Bilingual Post Generation** -- Produces complete blog posts in English and Spanish simultaneously, with proper Hugo front matter for each language.
- **Self-Review Loop** -- After generating content, Mikalia reviews her own work with a stricter temperature setting and iterates until quality standards are met.
- **Hugo Formatting** -- Outputs posts as Hugo page bundles compatible with the Blowfish theme, ready for deployment.
- **GitHub Integration** -- Commits and pushes directly to the blog repository, or creates pull requests for human review (F3 roadmap).
- **Telegram Notifications** -- Sends real-time alerts when posts are published, PRs are created, or errors occur.
- **Interactive Mode** -- A guided, conversational CLI experience for generating posts step by step.

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

Mikalia Bot uses a Click-based CLI with four main commands.

### `post` -- Generate and publish a blog post

```bash
# Generate and publish (full pipeline)
python -m mikalia post --topic "Building AI Agents with Python"

# Generate with a specific category and tags
python -m mikalia post --topic "My Topic" --category ai --tags "claude,agents,python"

# Dry run: generate and save locally, do not push
python -m mikalia post --topic "My Topic" --dry-run

# Preview: display in terminal only, do not save or push
python -m mikalia post --topic "My Topic" --preview
```

### `interactive` -- Guided post creation

```bash
python -m mikalia interactive
```

Mikalia walks you through topic selection, category, and tags interactively.

### `config` -- View and validate configuration

```bash
# Show current configuration
python -m mikalia config --show

# Validate that all required settings are present
python -m mikalia config --validate
```

### `health` -- Check all connections

```bash
python -m mikalia health
```

Verifies the Anthropic API key, MIKALIA.md personality file, blog repository path, GitHub App credentials, and Telegram configuration.

---

## Architecture

```
+---------------------+
|    CLI (Click)      |    <-- User runs commands here
+---------------------+
          |
          v
+---------------------+       +---------------------+
|   PostGenerator     | ----> |   MikaliaClient     |
|   (orchestration)   |       |   (Claude API)      |
+---------------------+       +---------------------+
          |
          v
+---------------------+
|   SelfReview        |    <-- Reviews and iterates on content
+---------------------+
          |
          v
+---------------------+       +---------------------+
|   HugoFormatter     | ----> |   GitOperations     |
|   (front matter +   |       |   (commit + push)   |
|    page bundles)    |       +---------------------+
+---------------------+               |
                                       v
                              +---------------------+
                              |   GitHub App Auth   |
                              |   (JWT / install    |
                              |    token)           |
                              +---------------------+
                                       |
                                       v
                              +---------------------+
                              |   Notifier          |
                              |   (Telegram, etc.)  |
                              +---------------------+
```

---

## Project Structure

```
mikalia-bot/
|-- mikalia/
|   |-- __init__.py
|   |-- __main__.py              # Entry point: python -m mikalia
|   |-- cli.py                   # Click commands (post, interactive, config, health)
|   |-- config.py                # Configuration loader (config.yaml + .env)
|   |-- personality.py           # Loads MIKALIA.md system prompt
|   |-- interactive.py           # Interactive mode logic
|   |-- agent/
|   |   |-- __init__.py
|   |-- generation/
|   |   |-- __init__.py
|   |   |-- client.py            # Claude API wrapper (MikaliaClient)
|   |   |-- post_generator.py    # Orchestrates post generation
|   |   |-- self_review.py       # Self-review loop
|   |-- publishing/
|   |   |-- __init__.py
|   |   |-- hugo_formatter.py    # Formats posts as Hugo page bundles
|   |   |-- git_ops.py           # Git commit, push, sync operations
|   |   |-- github_app.py        # GitHub App JWT authentication
|   |-- notifications/
|   |   |-- __init__.py
|   |   |-- notifier.py          # Notification dispatcher
|   |   |-- telegram.py          # Telegram channel implementation
|   |-- utils/
|       |-- __init__.py
|       |-- logger.py            # Rich-powered logging
|-- tests/
|   |-- __init__.py
|-- templates/                   # Prompt and post templates
|-- prompts/                     # System and generation prompts
|-- docs/                        # Additional documentation
|-- config.yaml                  # Central configuration file
|-- requirements.txt             # Python dependencies
|-- MIKALIA.md                   # Mikalia's personality and system prompt
|-- CLAUDIA.md                   # Development guidelines
|-- .env.example                 # Environment variable template
|-- .github/
|   |-- workflows/
|       |-- test.yml             # CI pipeline
|-- LICENSE
|-- README.md
```

---

## Configuration

Mikalia Bot uses two configuration sources: `config.yaml` for general settings and `.env` for secrets.

### config.yaml

Controls model parameters, blog paths, Git behavior, GitHub settings, and notification preferences. Key sections:

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
  commit_prefix: "..."

telegram:
  enabled: false
```

### .env

Contains sensitive values that must not be committed to version control:

```
ANTHROPIC_API_KEY=sk-ant-...
BLOG_REPO_PATH=/path/to/blog/repo
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/path/to/key.pem
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_CHAT_ID=-100123456789
```

---

## Roadmap

### F1 -- Direct Publishing (current)

Mikalia generates posts and pushes directly to the main branch. Suitable for trusted, single-author workflows.

### F2 -- Pull Request Workflow

Mikalia creates feature branches and opens pull requests instead of pushing to main. Human review is required before merging.

### F3 -- Full Autonomy with Guardrails

Mikalia operates on a schedule, selects topics autonomously, creates PRs with labels, and handles multiple content types (posts, fixes, documentation). Includes branch prefixes (`mikalia/post`, `mikalia/fix`, `mikalia/feat`, `mikalia/docs`) and automatic PR labeling.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Credits

Created by **Miguel "Mikata" Mata** at [Mikata AI Lab](https://mikata-ai-lab.github.io).

Powered by the [Claude API](https://docs.anthropic.com/en/docs/welcome) from Anthropic.
