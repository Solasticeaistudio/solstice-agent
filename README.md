<p align="center">
  <img src="assets/solstice-logo.svg" alt="Solstice Agent" width="400">
</p>

<h1 align="center">Solstice Agent</h1>

<p align="center">An AI agent framework that actually does things.</p>

<p align="center">
  <a href="https://pypi.org/project/solstice-agent/"><img src="https://img.shields.io/pypi/v/solstice-agent?color=8b5cf6&style=flat-square" alt="PyPI"></a>
  <a href="https://pypi.org/project/solstice-agent/"><img src="https://img.shields.io/pypi/pyversions/solstice-agent?color=70e1ff&style=flat-square" alt="Python"></a>
  <a href="https://github.com/Solasticeaistudio/solstice-agent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Solasticeaistudio/solstice-agent?color=10b981&style=flat-square" alt="License"></a>
  <a href="https://github.com/Solasticeaistudio/solstice-agent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Solasticeaistudio/solstice-agent/ci.yml?style=flat-square&label=CI" alt="CI"></a>
</p>

Not a chatbot wrapper. Not a webhook proxy. An autonomous agent with 72 built-in tools, 4 LLM providers, multi-agent routing, headless browser control, voice (TTS/STT), persistent memory, multimodal vision, autonomous API discovery, a skill system, cron scheduling, LLM context compaction — and a 21-channel messaging gateway.

```
pip install solstice-agent
```

---

## 30-Second Demo

```bash
export OPENAI_API_KEY=sk-...
solstice-agent
```

```
Solstice Agent v0.1.0
openai / gpt-4o
Tools: 72 loaded | Streaming: on

> I need to send an SMS
# Agent calls registry_search("SMS") → finds Twilio, SendGrid, Resend
# Then registry_connect("twilio") → auto-connects Blackbox with stored creds

> Connect to https://api.example.com and show me what it can do
# Agent calls blackbox_connect, blackbox_discover, blackbox_fingerprint
# Maps the entire API autonomously, reports endpoints and capabilities

> Navigate to hackernews and read the top stories
# Agent calls browser_navigate, browser_read — real headless Chrome

> Remember that my preferred language is Python
# Saved to disk. Still there next session.

> Look at screenshot.png and describe what you see
# Agent processes the image through the LLM's vision model
```

The agent doesn't guess. It uses tools.

---

## Why This Exists

OpenAI paid $205M for OpenClaw — an open-source project that routes messages from messaging platforms to an LLM and pipes the response back. That's a webhook proxy with a personality layer.

Solstice Agent is what an AI agent framework should actually look like:

| | OpenClaw | Solstice Agent |
|---|---------|---------------|
| Tools | File access, scripts | 72 built-in (files, terminal, web, browser, voice, screen capture, recording, Docker sandbox, presence, memory, API discovery, API registry, skills, cron) |
| API discovery | None — write a skill per API | **Autonomous** — point at any URL, it maps and operates it. Registry with 25 pre-loaded APIs searchable by capability |
| Browser | Sandboxed automation | Full Playwright (navigate, click, type, screenshot, JS eval) |
| Voice | ElevenLabs TTS | ElevenLabs TTS + Whisper STT (bidirectional) |
| Vision | Not built-in | Native multimodal — pass images to any provider |
| Memory | Markdown files | JSON persistence — facts + conversations, cross-session |
| Providers | Primarily OpenAI | OpenAI, Anthropic, Gemini, Ollama (local) |
| Channels | ~21 | **21** (WhatsApp, Telegram, Discord, Slack, Email, Teams, iMessage, Signal, Matrix, Google Chat, IRC, Mattermost, LINE, Twitch, Messenger, Twitter/X, Reddit, Nostr, WebChat, Feishu/Lark, Generic Webhook) |
| Multi-agent | Full workspace isolation | **Config-driven routing** — per-agent tools, personality, provider, per-sender isolation |
| Context management | Hard trim at 128K | **LLM-summarized compaction** — preserves key facts across long sessions |
| Security | [CVE-2026-25253 RCE](https://creati.ai/ai-news/2026-02-11/openclaw-open-source-ai-agent-viral-145k-github-stars/), 30K exposed instances, 20% malicious skills | **Defense-in-depth** — SSRF protection, path sandboxing, gateway auth, container isolation, command safety, input sanitization ([details](#security)) |
| Install | Docker required | `pip install` and go |
| Codebase | ~430K lines | **~8K lines** — same capabilities, 50x less code |

---

## Built-in Tools (72)

### File Operations
| Tool | What it does |
|------|-------------|
| `read_file` | Read a file with line numbers |
| `write_file` | Create a new file (with parent dirs) |
| `edit_file` | Surgical find/replace — changes only what you specify |
| `apply_patch` | Multi-hunk structured patches across one or more files |
| `list_files` | List directory contents with glob patterns |
| `delete_file` | Delete a file |
| `grep_files` | Search file contents by regex pattern |
| `find_files` | Find files by name pattern across directories |

### Terminal
| Tool | What it does |
|------|-------------|
| `run_command` | Execute shell commands — blocks until complete |
| `run_background` | Start a long-running process (dev servers, watchers) |
| `bg_status` | List all background sessions with status and PID |
| `bg_log` | Read output from a background session |
| `bg_write` | Send stdin to a background session |
| `bg_kill` | Kill a background session |

### Web
| Tool | What it does |
|------|-------------|
| `web_search` | Search the web via DuckDuckGo (no API key) |
| `fetch_url` | Fetch and extract text from any URL |

### Blackbox API Discovery
| Tool | What it does |
|------|-------------|
| `blackbox_connect` | Connect to any HTTP API endpoint |
| `blackbox_discover` | Auto-detect OpenAPI/Swagger docs |
| `blackbox_fingerprint` | Probe supported methods, latency, auth, error patterns |
| `blackbox_spider` | Crawl and map all API endpoints (scope-locked) |
| `blackbox_pull` | GET data from any discovered endpoint |
| `blackbox_push` | POST/PUT/PATCH/DELETE (requires explicit write access) |

Point Sol at any API. It figures out what the API can do. Then you just talk to it.

### API Registry / Marketplace
| Tool | What it does |
|------|-------------|
| `registry_search` | Search the catalog by capability — "I need SMS" finds Twilio, SendGrid |
| `registry_add` | Register a new API with URL, auth, tags, and pricing info |
| `registry_get` | Get full details on a registered API (URL, auth, stats, endpoints) |
| `registry_connect` | One-step: pull API from registry and auto-connect Blackbox with stored creds |
| `registry_stats` | Quality report — latency, success rate, health grade |
| `registry_remove` | Remove an API from the catalog |

Ships with 25 pre-loaded APIs across 9 categories (weather, communication, payments, maps, AI, devtools, data, media, productivity). Agents search by what they need, connect in one call, and quality stats are tracked automatically.

### Browser Automation
| Tool | What it does |
|------|-------------|
| `browser_navigate` | Load a URL in headless Chrome |
| `browser_read` | Extract text content (full page or CSS selector) |
| `browser_click` | Click elements by CSS selector |
| `browser_type` | Type into input fields, optionally submit |
| `browser_screenshot` | Capture page screenshots |
| `browser_eval` | Execute JavaScript in page context |
| `browser_close` | Close browser and free resources |

### Voice
| Tool | What it does |
|------|-------------|
| `voice_speak` | Text-to-speech via ElevenLabs |
| `voice_listen` | Speech-to-text via Whisper (file or microphone) |
| `voice_list_voices` | List available ElevenLabs voices |

### Persistent Memory
| Tool | What it does |
|------|-------------|
| `memory_remember` | Save a fact that persists across sessions |
| `memory_recall` | Recall a saved fact (with fuzzy matching) |
| `memory_forget` | Remove a saved memory |
| `memory_list_conversations` | List all saved conversation sessions |

### Skills
| Tool | What it does |
|------|-------------|
| `skill_get` | Load a skill guide (Tier 2 or Tier 3) to learn a domain-specific workflow |
| `skill_list` | List all available skill guides with descriptions |

### Screen Capture + Annotation (A2UI)
| Tool | What it does |
|------|-------------|
| `screen_capture` | Screenshot all monitors (stitched), specific display, or region |
| `screen_capture_window` | Capture a specific window by title (cross-platform) |
| `screen_list_displays` | List all connected monitors with resolution and position |
| `screen_annotate` | Annotate images with circles, arrows, rectangles, text, highlights |

### Docker Sandbox
| Tool | What it does |
|------|-------------|
| `sandbox_run` | One-shot container execution — secure defaults, no network, auto-remove |
| `sandbox_start` | Start a persistent container for multi-step workflows |
| `sandbox_exec` | Execute command in a running sandbox |
| `sandbox_stop` | Stop and remove a sandbox container |
| `sandbox_list` | List all running sandbox containers |
| `sandbox_copy_in` | Copy file from host into container |
| `sandbox_copy_out` | Copy file from container to host |

### Continuous Voice + Wake Word
| Tool | What it does |
|------|-------------|
| `voice_start_listening` | Always-on mic with VAD and wake word detection ("hey sol") |
| `voice_stop_listening` | Stop listening and release the microphone |
| `voice_listening_status` | Get listening state, wake words, device info |
| `voice_set_wake_words` | Update wake words live |
| `voice_get_transcript` | Get the most recent speech transcript |

### Platform Presence
| Tool | What it does |
|------|-------------|
| `presence_notify` | System notification (Windows toast, macOS notification center, Linux) |
| `presence_set_status` | Update agent status indicator (active, idle, busy, listening) |
| `presence_get_clipboard` | Read system clipboard text |
| `presence_set_clipboard` | Write text to system clipboard |

### Screen + Camera Recording
| Tool | What it does |
|------|-------------|
| `recording_start` | Record screen as MP4 video (quality presets: low/medium/high) |
| `recording_stop` | Stop recording and finalize video file |
| `recording_status` | Get recording state, duration, file size |
| `camera_capture` | Capture single frame from webcam |
| `camera_list` | List available camera devices |

### Scheduling (Cron)
| Tool | What it does |
|------|-------------|
| `cron_add` | Schedule a recurring task ("every 6h", "every day at 9am", "cron 0 */6 * * *") |
| `cron_list` | List all scheduled jobs with status and next run time |
| `cron_remove` | Remove a scheduled job by ID |

---

## Skills System

Teach Sol new workflows by dropping markdown files into `~/.solstice-agent/skills/`.

```markdown
---
name: github-pr
description: Create and manage GitHub pull requests
tools: [run_command]
trigger: pr|pull request|merge
---
# PR Workflow
1. Check branch: `git branch --show-current`
2. Create PR: `gh pr create --title "..." --body "..."`

<!-- tier3 -->
Full gh pr reference docs here...
```

**Three-tier loading** keeps token usage minimal:
- **Tier 1** — Name + description always in system prompt (~30 tokens per skill)
- **Tier 2** — Full guide loaded on-demand via `skill_get` tool
- **Tier 3** — Extended reference docs below `<!-- tier3 -->` marker

Skills with `trigger` patterns auto-inject when the user's message matches.

---

## Scheduling

Run tasks autonomously on a timer. Jobs persist to `~/.solstice-agent/cron/jobs.json` and survive restarts.

```bash
# Quick-schedule from CLI
solstice-agent --cron "every 6h" "check my email and summarize"

# Or let the agent schedule itself
> Schedule a daily summary of my GitHub notifications at 9am
# Agent calls cron_add("every day at 9am", "summarize my github notifications")
```

**Supported schedule formats:**
- `every 6h` / `every 30m` / `every 2d` — interval
- `every day at 9am` — daily at time
- `every monday at 5pm` — weekly
- `at 3pm` — one-shot (auto-disables after execution)
- `cron 0 */6 * * *` — standard 5-field cron

Results deliver to any gateway channel or save to `~/.solstice-agent/cron/results/`. Failed jobs use exponential backoff and auto-disable after 3 consecutive failures.

---

## Context Compaction

Instead of hard-trimming conversation history at 40 messages (losing all context), Sol summarizes older messages into a compact digest when approaching the model's context window.

- Automatic — triggers at 75% of the model's context window
- Preserves key facts, decisions, file paths, errors, and user preferences
- Never breaks tool call/result pairs when splitting history
- Nested summaries accumulate (old summaries get re-summarized)
- Falls back to hard trim if summarization fails

Model context windows are auto-detected (128K for GPT-4o, 200K for Claude, 1M for Gemini).

---

## Multi-Agent Routing

Define multiple agents with different personalities, tools, and providers. Route messages based on channel, sender, content, or command prefix.

```yaml
# solstice-agent.yaml
provider: openai
model: gpt-4o

agents:
  default:
    personality: default

  coder:
    provider: anthropic
    model: claude-opus-4-6
    personality: coder
    temperature: 0.2
    tools:
      enable_browser: false
      enable_voice: false

  safe:
    tools:
      enable_terminal: false
      enable_blackbox: false

  research:
    personality:
      name: "Nova"
      role: "research analyst"
      tone: "Thorough, analytical, cites sources"
      rules:
        - "Always use web_search before answering factual questions"
    tools:
      enable_terminal: false

routing:
  strategy: channel
  default: default
  rules:
    discord: coder
    email: safe
    telegram: research
```

**Routing strategies:** `channel` (route by platform), `sender` (route by user ID), `content` (regex matching on message), `prefix` (command prefix like `!code`).

**Per-sender isolation:** Each sender gets their own agent instance with independent conversation history. No cross-talk.

```bash
# CLI: select agent by name
solstice-agent --agent coder "refactor this function"

# List available agents
solstice-agent --list-agents

# API: specify agent + sender
curl -X POST localhost:5050/chat \
  -H "Authorization: Bearer $SOL_GATEWAY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "fix the login bug", "agent": "coder", "sender_id": "alice"}'

# List agents + routing config
curl -H "Authorization: Bearer $SOL_GATEWAY_TOKEN" localhost:5050/agents
```

---

## Multimodal (Vision)

Pass images alongside text. Works with all providers that support vision.

```bash
# One-shot with image
solstice-agent --image screenshot.png "What's in this image?"

# Multiple images
solstice-agent -i design.png -i mockup.png "Compare these designs"
```

```python
# Python API
response = agent.chat("Describe this diagram", images=["architecture.png"])
```

---

## Providers

Bring your own keys. Or bring no keys at all — run local with Ollama.

```bash
# OpenAI (GPT-4o, o1, o3)
export OPENAI_API_KEY=sk-...
solstice-agent

# Anthropic (Claude Opus, Sonnet, Haiku)
export ANTHROPIC_API_KEY=sk-ant-...
solstice-agent --provider anthropic

# Gemini (2.5 Pro, Flash) with Google Search grounding
export GEMINI_API_KEY=AI...
solstice-agent --provider gemini

# Ollama (local, no API key, no data leaves your machine)
solstice-agent --provider ollama --model llama3.1

# Any OpenAI-compatible API (LMStudio, Together, vLLM, etc.)
solstice-agent --provider openai --model your-model --api-key your-key
```

---

## Persistent Memory

Conversations and facts survive restarts. Stored in `~/.solstice-agent/memory/`.

```bash
# Resume your last conversation
solstice-agent --continue

# The agent remembers things you tell it
> Remember that the production database is on port 5432
# Next session:
> What port is the production database on?
# "5432 — you told me that last session."
```

---

## Messaging Gateway — 21 Channels

Talk to your agent from any messaging platform. Enable one or all — each channel is independent.

| Channel | Protocol | Notes |
|---------|----------|-------|
| **WhatsApp** | Twilio API | Reuses existing Twilio creds |
| **Telegram** | Bot API (httpx) | Zero extra deps |
| **Discord** | discord.py bot | Background WebSocket thread |
| **Slack** | Events API + WebClient | 3-second async pattern |
| **Email** | IMAP + SMTP | Poll-based inbound |
| **Microsoft Teams** | Bot Framework + OAuth2 | Azure AD app registration |
| **iMessage** | BlueBubbles bridge | macOS + BlueBubbles server required |
| **Signal** | signal-cli-rest-api | Self-hosted Signal bridge |
| **Matrix** | Client-Server API (httpx) | Works with any homeserver |
| **Google Chat** | Workspace API | Service account auth |
| **IRC** | Raw socket | Background thread, auto-reconnect |
| **Mattermost** | REST API + webhooks | Self-hosted Slack alternative |
| **LINE** | Messaging API | Popular in Japan/SE Asia |
| **Twitch** | IRC-based chat | Stream chat integration |
| **Facebook Messenger** | Graph API | Page access token |
| **Twitter / X** | DM API v2 | OAuth 2.0 User Context |
| **Reddit** | OAuth2 API | Comment + DM replies |
| **Nostr** | NIP-04 DMs | Decentralized, censorship-resistant |
| **WebChat** | HTTP POST | Embeddable web widget |
| **Feishu / Lark** | ByteDance API | Popular in China/APAC |
| **Generic Webhook** | Any JSON | Catch-all for custom integrations |

```bash
# Example: Telegram
export GATEWAY_TELEGRAM_ENABLED=true
export GATEWAY_TELEGRAM_BOT_TOKEN=your-token
solstice-gateway

# Example: Discord
export GATEWAY_DISCORD_ENABLED=true
export GATEWAY_DISCORD_BOT_TOKEN=your-token
export GATEWAY_DISCORD_CHANNEL_IDS=123456789
solstice-gateway

# Example: Slack
export GATEWAY_SLACK_ENABLED=true
export GATEWAY_SLACK_BOT_TOKEN=xoxb-your-token
export GATEWAY_SLACK_SIGNING_SECRET=your-secret
solstice-gateway
```

Every channel follows the same pattern: `GATEWAY_{CHANNEL}_ENABLED=true` + platform-specific credentials.

---

## Personalities

Built-in: `default` (direct, witty) and `coder` (technical, read-before-edit). Use them by name in YAML config or define inline:

```yaml
# Reference by name
agents:
  helper:
    personality: coder

  # Or define inline
  research:
    personality:
      name: "Nova"
      role: "research analyst"
      tone: "Thorough, analytical, cites sources"
      rules:
        - "Always use web_search before answering factual questions"
```

```python
# Python API
from solstice_agent.agent import Agent, Personality

personality = Personality(
    name="Atlas",
    role="Senior software engineer",
    tone="Direct, technical, no hand-holding",
    rules=[
        "Read code before suggesting changes",
        "Run tests after every edit",
        "Explain trade-offs, not just solutions",
    ],
)

agent = Agent(provider=provider, personality=personality)
```

---

## Custom Tools

Add your own in 3 lines:

```python
agent.register_tool(
    "get_weather",
    lambda city: f"72F and sunny in {city}",
    {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
)
```

---

## Installation

```bash
# Core
pip install solstice-agent

# With provider
pip install solstice-agent[openai]
pip install solstice-agent[anthropic]
pip install solstice-agent[gemini]

# With extras
pip install solstice-agent[browser]     # Playwright headless browser
pip install solstice-agent[voice]       # ElevenLabs + Whisper + continuous listening
pip install solstice-agent[screen]      # Screen capture + annotation
pip install solstice-agent[recording]   # Screen/camera recording (OpenCV)
pip install solstice-agent[docker]      # Docker sandbox isolation
pip install solstice-agent[tray]        # System tray + notifications + clipboard
pip install solstice-agent[gateway]     # Messaging channels
pip install solstice-agent[web]         # DuckDuckGo search

# Everything
pip install solstice-agent[all]

# Browser requires one extra step:
playwright install chromium
```

---

## Architecture

```
solstice_agent/
    agent/
        core.py              # Tool-calling loop + conversation memory
        personality.py       # Character system
        memory.py            # Persistent cross-session memory
        skills.py            # 3-tier skill/plugin system
        scheduler.py         # Cron scheduling (persistent, background)
        compactor.py         # LLM-based context summarization
        router.py            # Multi-agent routing + agent pool
        personalities.py     # Personality registry
        providers/
            base.py          # Abstract LLM interface + multimodal encoding
            openai_provider.py
            anthropic_provider.py
            gemini_provider.py
            ollama_provider.py
    tools/
        registry.py          # Dynamic tool registration
        file_ops.py          # read, write, edit, apply_patch, grep, find, list, delete
        terminal.py          # Shell execution + background process management
        web.py               # Search + fetch
        blackbox.py          # Autonomous API discovery + interaction
        api_registry.py      # API catalog, search, credential management
        seed_catalog.json    # 25 pre-loaded APIs
        browser.py           # Headless Chrome automation
        voice.py             # ElevenLabs TTS + Whisper STT
        voice_continuous.py  # Always-on mic + wake word + VAD
        screen.py            # Screen capture + display enum + annotation
        recording.py         # Screen recording (MP4) + camera capture
        docker_sandbox.py    # Isolated container execution
        presence.py          # Notifications + clipboard + tray status
        security.py          # SSRF protection, path sandboxing, input validation
    tray.py                  # System tray entry point
    gateway/
        manager.py           # Channel orchestrator (21 channels)
        channels/            # One adapter per platform
            whatsapp_channel.py   telegram_channel.py
            discord_channel.py    slack_channel.py
            email_channel.py      teams_channel.py
            imessage_channel.py   signal_channel.py
            matrix_channel.py     google_chat_channel.py
            irc_channel.py        mattermost_channel.py
            line_channel.py       twitch_channel.py
            messenger_channel.py  twitter_channel.py
            reddit_channel.py     nostr_channel.py
            webchat_channel.py    feishu_channel.py
            webhook_channel.py
    cli.py                   # Terminal REPL
    server.py                # Gateway HTTP server
    config.py                # YAML + env var config
```

---

## Security

Solstice Agent treats security as a first-class concern — not an afterthought. Every tool category has layered defenses.

### Network (SSRF Protection)
All outbound HTTP tools (`fetch_url`, `blackbox_connect`, `browser_navigate`) are gated by `validate_url()`:
- **Blocked:** private/reserved IPs (10.x, 172.16.x, 192.168.x, 127.0.0.1)
- **Blocked:** cloud metadata endpoints (169.254.169.254, metadata.google.internal)
- **Blocked:** dangerous schemes (file://, javascript:, data://)
- **Blocked:** common internal service ports (Redis 6379, Postgres 5432, Mongo 27017, etc.)
- **Allowed:** http:// and https:// to public endpoints only

### File System (Path Sandboxing)
All file operations (`read_file`, `write_file`, `edit_file`, `delete_file`, `apply_patch`) are gated by `validate_path()`:
- **Workspace boundary** — operations restricted to the working directory tree
- **Symlink resolution** — `os.path.realpath()` prevents symlink-based escapes
- **Sensitive file blocklist** — `.ssh/`, `.gnupg/`, `.aws/credentials`, `.env`, `.docker/config.json` are always blocked
- Set at startup via `set_workspace_root()` in the CLI

### Terminal (Command Safety)
Shell commands go through a pattern-based safety check before execution:
- **Destructive operations** — `rm -rf`, `mkfs`, `dd`, `git push --force`, `DROP TABLE`
- **Interpreter evasion** — `python -c "os.system(...)"`, `node -e`, `base64 -d | sh`
- **Credential access** — `.ssh/authorized_keys`, `printenv`, `crontab -e`
- **Network exfiltration** — `nc`, `ncat`, `curl | sh`, `wget | python`
- Dangerous commands require explicit user confirmation via callback (CLI prompts, gateway can wire custom flows)
- Background processes capped at 10 concurrent sessions

### Gateway (Authentication)
The HTTP gateway server (`solstice-gateway`) is locked down by default:
- **Default bind:** `127.0.0.1` (localhost only — not `0.0.0.0`)
- **Token auth:** Bearer token required on all endpoints when binding to a network interface
- **Auto-generated tokens:** if you bind to `0.0.0.0` without providing a token, one is generated and displayed
- **Minimal health endpoint:** `/health` returns `{"status": "ok"}` only — no tool lists, provider names, or internal state

```bash
# Localhost (no auth needed)
solstice-gateway

# Network-accessible (auto-generates token)
solstice-gateway --host 0.0.0.0

# Explicit token
solstice-gateway --host 0.0.0.0 --auth-token your-secret-token
# or: SOL_GATEWAY_TOKEN=your-secret-token solstice-gateway --host 0.0.0.0

# Authenticated request
curl -X POST localhost:5050/chat \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"message": "hello"}'
```

### Docker Sandbox (Container Isolation)
Sandboxed containers run with secure defaults and strict boundaries:
- **No network** by default (`network_disabled=True`)
- **Resource caps** — memory limit (512MB), CPU limit (1 core)
- **No privilege escalation** — `security_opt=["no-new-privileges"]`
- **Volume mounts restricted to CWD** — symlinks resolved with `realpath` before validation
- **Container label verification** — `sandbox_exec`/`sandbox_stop` only operate on containers created by Solstice (verified by `sol.sandbox` label)
- **Copy restrictions** — `sandbox_copy_in` and `sandbox_copy_out` restricted to the working directory

### Browser (JavaScript Restrictions)
The headless browser tools have guardrails:
- **URL scheme allowlist** — `browser_navigate` only accepts `http://` and `https://`
- **JS eval restrictions** — `browser_eval` blocks `fetch()`, `XMLHttpRequest`, cookies, localStorage, eval chains, WebSocket, and other dangerous APIs
- **Error sanitization** — no stack traces or tokens leaked in error messages

### Screen Capture (Input Sanitization)
- **Window title sanitization** — `screen_capture_window` validates titles against a strict character allowlist before passing to platform commands (PowerShell, osascript, xdotool), preventing command injection
- **Length limit** — 200 characters max

### Additional Controls
- **Cron job limit** — maximum 20 scheduled jobs to prevent resource exhaustion
- **Memory path traversal protection** — session IDs sanitized and resolved paths verified within the conversations directory
- **Error message sanitization** — all tool error messages use generic text; stack traces with potential secrets go to `log.debug` only

### Architecture

All security validation is centralized in `solstice_agent/tools/security.py` with two main functions:
- `validate_url(url, allow_private=False)` — SSRF protection for any outbound HTTP
- `validate_path(path, operation)` — workspace boundary + sensitive file blocking

This makes it easy to audit, update, and test security rules in one place.

---

## Roadmap

- [x] v0.1 — Agent core, 4 providers, 72 tools, streaming, multi-hunk patching, background processes, code search, screen capture, screen recording, Docker sandboxing, system tray, always-on voice, CLI, gateway, multimodal, voice, browser, memory, skills, cron, context compaction, multi-agent routing, API registry
- [ ] v0.2 — Community skill marketplace, OpenRouter provider, MCP client
- [ ] v0.3 — Local model fine-tuning hooks, agent-to-agent delegation
- [ ] v1.0 — Stable API, comprehensive docs, conference-ready

---

## Contributing

PRs welcome. The codebase is intentionally simple — no framework bloat, no over-abstraction.

```bash
git clone https://github.com/solstice-studio/solstice-agent
cd solstice-agent
pip install -e ".[dev,all]"
pytest
```

---

## License

MIT. Use it, fork it, build on it.

---

Built by [Solstice Studio](https://solsticestudio.ai). The same team behind IRIS, Helios, Ares, Sentinel, and the Solstice Enterprise Intelligence Mesh.
