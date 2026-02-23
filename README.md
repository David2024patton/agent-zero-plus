<div align="center">

# `Agent 0+`

### A personal AI assistant framework — forked from Agent Zero, enhanced with 30+ tools, self-healing intelligence, and a technician problem-solving mindset.

[![GitHub](https://img.shields.io/badge/GitHub-Agent%200%2B-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/David2024patton/agent-zero)

</div>

---

## What is Agent 0+?

**Agent 0+** is a heavily enhanced fork of [Agent Zero](https://github.com/frdel/agent-zero) — an open-source, fully autonomous AI agent framework. While Agent Zero provides the core agentic loop, Agent 0+ adds:

- **30+ custom tools** for real-world tasks (email, GitHub, weather, video analysis, image generation, and more)
- **Self-healing technician mindset** — the agent diagnoses errors, installs missing dependencies, and searches the web for solutions
- **Plugin system** for messaging channels (Discord, Slack, WhatsApp, Telegram, Matrix)
- **Enhanced browser backend** with multiple provider support
- **Skill-based architecture** using the open `SKILL.md` standard

> **Agent 0+ thinks like a technician.** When something fails, it reads the error, diagnoses the root cause, installs what's needed, tries alternative approaches, and verifies the fix — all autonomously.

---

## ⚡ Quick Start

```bash
# Clone the repo
git clone https://github.com/David2024patton/agent-zero.git
cd agent-zero

# Copy environment template
cp .env.example .env
# Edit .env with your API keys

# Pull and run with Docker
docker compose up -d

# Visit http://localhost:50001 to start
```

### Requirements
- Docker & Docker Compose
- At least one LLM API key (OpenAI, Google Gemini, Z.AI, Mistral, or any LiteLLM-supported provider)

---

## 🧰 30+ Custom Tools

Agent 0+ ships with tools that go far beyond the Agent Zero defaults:

### Communication & Messaging
| Tool | Description |
|------|-------------|
| `email_tool` | Send/receive emails via SMTP/IMAP (configurable hosts) |
| `message_channel` | Unified messaging across Discord, Slack, Telegram, WhatsApp, Matrix |

### Developer & DevOps
| Tool | Description |
|------|-------------|
| `github_tool` | Repos, issues, PRs, file contents, gists, workflow listing |
| `hostinger_tool` | DNS records, SSL status, hosting management |
| `browser_agent` | Full browser automation with multiple backend support |
| `browser_read` | Read and extract content from web pages |
| `document_to_markdown` | Convert documents to markdown format |

### AI & LLM Integration
| Tool | Description |
|------|-------------|
| `gemini_tool` | Google Gemini API (generate, analyze, count tokens) |
| `mistral_tool` | Mistral AI API integration |
| `zai_tool` | Z.AI API integration |
| `huggingface_tool` | Model inference, search models/datasets |
| `image_gen_tool` | DALL-E image generation, editing, and variations |
| `whisper_tool` | OpenAI Whisper speech-to-text transcription |
| `summarize_tool` | URL/text summarization (bullet, paragraph, academic styles) |
| `swarm` | Multi-agent parallel analysis with tiered model selection |

### Productivity
| Tool | Description |
|------|-------------|
| `notion_tool` | Pages, databases, blocks — full Notion API |
| `trello_tool` | Boards, cards, labels, search |

### Media & Data
| Tool | Description |
|------|-------------|
| `weather_tool` | Current weather & forecasts (metric/imperial, feels-like temp) |
| `video_transcript_tool` | YouTube transcripts, subtitles, keyword search |
| `video_frames_tool` | Extract frames, thumbnails, GIF conversion, resize |

### Skills (Auto-loaded)
| Skill | Description |
|-------|-------------|
| `system-report` | Generate PDF system health reports with CPU/RAM/disk charts |
| `search-engine` | Web search via SearXNG |
| `weather` | Weather lookups via wttr.in and Open-Meteo |
| `browser-agent` | Browser automation guidance |
| And 25+ more... | Email, GitHub, Notion, Trello, scheduler, etc. |

---

## 🧠 Self-Healing Technician Mindset

This is the core enhancement that sets Agent 0+ apart. The agent is instructed to think like a **real technician**:

### When something fails:
1. **Read the error** — don't blindly retry
2. **Diagnose the cause** — missing package? bad config? wrong path?
3. **Fix it** — install deps, set env vars, try alternatives
4. **Verify the fix** — confirm it actually worked
5. **Move on** — treat every error as a puzzle to solve

### When it doesn't know something:
- **Uses `search_engine`** to Google the error message, library docs, or technique
- **Reads Stack Overflow, GitHub issues, docs** — just like a real technician
- **Never guesses blindly** — always researches before attempting unfamiliar fixes

### Self-repair rules:
- Never repeats the same failing action more than twice without changing approach
- If approach A fails, tries approach B (different library, method, or fallback)
- If both fail, searches the web for how others solved the same problem
- Auto-installs missing packages (`pip install`, `apt-get install`, `npm install`)

---

## 🔌 Plugin System

Agent 0+ includes a plugin architecture for messaging channels:

| Plugin | Description |
|--------|-------------|
| `discord_channel` | Discord bot integration |
| `slack_channel` | Slack workspace integration |
| `whatsapp_channel` | WhatsApp messaging |
| `telegram_channel` | Telegram bot integration |
| `matrix_channel` | Matrix/Element integration |

Plugins are loaded automatically from the `plugins/` directory.

---

## 🛡️ Security

- **Secrets management** — API keys are stored encrypted and injected at runtime; the agent never sees raw credentials
- **Docker isolation** — all agent code runs inside a sandboxed Kali Linux container
- **`.gitignore` protection** — `.env`, `usr/`, and `tmp/` directories are excluded from git
- **No credentials in code** — all tools read secrets from environment variables

### Setting up your keys:

1. Copy `.env.example` to `.env`
2. Add your API keys to `.env`
3. Or use the Web UI: **Settings → External Services → Secrets**

Required keys depend on which tools you want to use:

| Key | Tools |
|-----|-------|
| `OPENAI_API_KEY` | image_gen, whisper, summarize |
| `GEMINI_API_KEY` | gemini_tool |
| `MISTRAL_API_KEY` | mistral_tool |
| `GITHUB_PERSONAL_ACCESS_TOKEN` | github_tool |
| `HUGGINGFACE_TOKEN` | huggingface_tool |
| `NOTION_API_KEY` | notion_tool |
| `TRELLO_API_KEY` + `TRELLO_TOKEN` | trello_tool |
| `HOSTINGER_API_TOKEN` | hostinger_tool |

---

## 📁 Project Structure

```
agent-zero/
├── prompts/                    # All system prompts (fully customizable)
│   ├── agent.system.main.*.md  # Core agent behavior + technician mindset
│   └── agent.system.tool.*.md  # Tool-specific prompts (30+)
├── python/
│   ├── tools/                  # Custom tool implementations
│   ├── helpers/                # Utilities (browser backend, TTS, plugins, etc.)
│   ├── api/                    # API endpoints
│   └── extensions/             # Extension hooks (pre/post LLM call)
├── plugins/                    # Messaging channel plugins
├── skills/                     # Built-in skills
├── usr/skills/                 # User skills (gitignored)
├── webui/                      # Web UI (HTML/CSS/JS)
├── conf/                       # Model providers config
└── docker-compose.yml          # Docker deployment
```

---

## ⚙️ Configuration

### Model Providers

Agent 0+ supports all LiteLLM-compatible providers:

- OpenAI, Google Gemini, Mistral, Z.AI, Anthropic
- Ollama (local), OpenRouter, CometAPI
- AWS Bedrock, Azure OpenAI
- And many more via LiteLLM

Configure in the Web UI under **Settings → Agent Settings** or via environment variables with the `A0_SET_` prefix.

### Browser Backend

Multiple browser automation backends are supported:
- Default Docker-based browser
- External browser connections
- Custom CDP endpoints

---

## 🔧 Customization

Everything is customizable:

- **Prompts** — Edit any file in `prompts/` to change agent behavior
- **Tools** — Add new tools in `python/tools/` with matching prompts
- **Skills** — Create `SKILL.md` files in `usr/skills/` for new capabilities
- **Plugins** — Add messaging channels in `plugins/`
- **Extensions** — Hook into the agent loop via `python/extensions/`

---

## 🙏 Credits

- Based on [Agent Zero](https://github.com/frdel/agent-zero) by [frdel](https://github.com/frdel)
- Enhanced by [David Patton](https://github.com/David2024patton)
- Uses the [SKILL.md standard](https://github.com/anthropics/claude-code) developed by Anthropic
- Powered by [LiteLLM](https://github.com/BerriAI/litellm) for multi-provider LLM support
</div>
<parameter name="EmptyFile">false
