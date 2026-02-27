<p align="center">
  <img src="assets/solstice-logo.png" alt="Sol" width="200">
</p>

<h1 align="center">Sol</h1>

<p align="center">Your personal AI agent. Install it, talk to it, let it work.</p>

<p align="center">
  <a href="https://pypi.org/project/solstice-agent/"><img src="https://img.shields.io/pypi/v/solstice-agent?color=8b5cf6&style=flat-square" alt="PyPI"></a>
  <a href="https://pypi.org/project/solstice-agent/"><img src="https://img.shields.io/pypi/pyversions/solstice-agent?color=70e1ff&style=flat-square" alt="Python"></a>
  <a href="https://github.com/Solasticeaistudio/solstice-agent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Solasticeaistudio/solstice-agent?color=10b981&style=flat-square" alt="License"></a>
  <a href="https://github.com/Solasticeaistudio/solstice-agent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Solasticeaistudio/solstice-agent/ci.yml?style=flat-square&label=CI" alt="CI"></a>
</p>

---

## What is Sol?

Sol is an AI that lives on your computer. You talk to it, and it does things — reads your files, browses the web, runs your code, sends you messages on WhatsApp, listens for your voice, schedules tasks while you sleep, and remembers everything across sessions. No cloud account needed. Your data stays on your machine.

### Quick Install

**Windows** (PowerShell):
```powershell
irm https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.ps1 | iex
```

**macOS / Linux**:
```bash
curl -fsSL https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.sh | bash
```

That's it. The installer handles Python detection, package install, and PATH setup. Then:

```
solstice-agent --setup    # Pick your AI provider
solstice-agent            # Start talking
```

---

## Talk to It

Sol starts as a chat in your terminal. Ask it things. Tell it to do things.

```
Sol v0.2.1
openai / gpt-4o
Tools: 72 loaded | Streaming: on

> What's on Hacker News right now?
# Sol opens a browser, reads the page, and tells you

> Remind me to check my email every morning at 9am
# Done. It'll run that task every day, even if you're not around.

> Remember that the production database is on port 5432
# Saved. It'll still know this next week.

> Look at screenshot.png and describe what you see
# Sol sees the image and describes it

> Connect to https://api.example.com and show me what it can do
# Sol discovers every endpoint, figures out auth, maps the whole API
```

---

## Talk to It by Voice

Say **"hey Sol"** and start talking. It listens through your microphone, understands you, and responds out loud. No buttons to press — just talk.

You can also change the wake word, choose from different voices, or use push-to-talk.

---

## Reach It From Anywhere

Sol connects to **21 messaging platforms**. Message it on WhatsApp and it responds. DM it on Discord. Email it. Text it on Telegram. It's the same agent everywhere — same memory, same tools, same personality.

**Supported platforms:** WhatsApp, Telegram, Discord, Slack, Email, Microsoft Teams, iMessage, Signal, Matrix, Google Chat, IRC, Mattermost, LINE, Twitch, Facebook Messenger, Twitter/X, Reddit, Nostr, WebChat, Feishu/Lark, and Generic Webhook.

Each platform takes one environment variable to enable:

```bash
# Example: connect Sol to Telegram
export GATEWAY_TELEGRAM_ENABLED=true
export GATEWAY_TELEGRAM_BOT_TOKEN=your-token
solstice-gateway
```

---

## What Can It Do?

Sol ships with **72 built-in tools** across 14 categories:

| Category | Tools | Examples |
|----------|-------|---------|
| **Files** | 8 | Read, write, edit, search, find, delete files on your machine |
| **Terminal** | 6 | Run commands, start background processes, monitor logs |
| **Web** | 2 | Search the internet, fetch any URL |
| **API Discovery** | 6 | Point Sol at any API — it maps every endpoint automatically |
| **API Registry** | 6 | 25 pre-loaded APIs (Twilio, Stripe, GitHub...) — search by need, connect in one call |
| **Browser** | 7 | Navigate, click, type, screenshot — real headless Chrome |
| **Voice** | 3 | Text-to-speech, speech-to-text, voice selection |
| **Continuous Voice** | 5 | Wake word ("hey Sol"), always-on listening, live transcript |
| **Memory** | 4 | Remember facts, recall them later, list past conversations |
| **Screen** | 4 | Screenshot your screen, capture specific windows, annotate images |
| **Recording** | 5 | Record your screen as video, capture from webcam |
| **Docker** | 7 | Run code in isolated containers — safe sandbox, no network |
| **Presence** | 4 | Desktop notifications, clipboard access, status indicator |
| **Scheduling** | 3 | Recurring tasks ("every 6h", "every Monday at 5pm", cron syntax) |

You don't need to know tool names. Just tell Sol what you want and it picks the right tools.

---

## Schedule Tasks

Sol can run tasks on a schedule, even when you're not around. Jobs persist through restarts.

```bash
# From the command line
solstice-agent --cron "every 6h" "check my email and summarize"

# Or just tell it
> Schedule a daily summary of my GitHub notifications at 9am
```

**Formats:** `every 6h`, `every day at 9am`, `every monday at 5pm`, `at 3pm` (one-shot), or standard cron (`0 */6 * * *`).

---

## Choose Your AI Provider

Sol works with 4 providers. Bring your own API key, or run completely local with Ollama — no key needed, nothing leaves your machine.

```bash
# OpenAI (default)
export OPENAI_API_KEY=sk-...
solstice-agent

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
solstice-agent --provider anthropic

# Google Gemini
export GEMINI_API_KEY=AI...
solstice-agent --provider gemini

# Ollama (fully local, no API key)
solstice-agent --provider ollama --model llama3.1
```

Any OpenAI-compatible API also works (LMStudio, Together, vLLM, etc.).

---

## It Remembers

Sol saves conversations and facts across sessions. Come back tomorrow and pick up where you left off.

```bash
# Resume your last conversation
solstice-agent --continue

# The agent remembers things you tell it
> Remember that my preferred language is Python
# Next session:
> What's my preferred language?
# "Python — you told me that last session."
```

---

## Give It a Personality

Sol comes with built-in personalities (`default`, `coder`, `researcher`, `creative`, `minimal`), or you can create your own. Define a name, a role, a tone, and rules it should follow.

---

## Install

**Recommended** — use the one-line installer (handles PATH automatically):

```powershell
# Windows (PowerShell)
irm https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.ps1 | iex

# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.sh | bash
```

**Manual install** — if you prefer pip directly:

```bash
pip install solstice-agent[all]

# Or pick what you need
pip install solstice-agent                # Core only
pip install solstice-agent[openai]        # + OpenAI provider
pip install solstice-agent[voice]         # + Voice (ElevenLabs + Whisper)
pip install solstice-agent[browser]       # + Headless Chrome
pip install solstice-agent[gateway]       # + Messaging channels
pip install solstice-agent[screen]        # + Screen capture
pip install solstice-agent[recording]     # + Screen/camera recording
pip install solstice-agent[docker]        # + Docker sandbox
pip install solstice-agent[tray]          # + System tray
pip install solstice-agent[web]           # + Web search

# Browser needs one extra step
playwright install chromium
```

> **Windows note:** If `solstice-agent` isn't recognized after pip install, your Python Scripts directory isn't on PATH. Use the one-line installer above — it fixes this automatically. Or run `python -m solstice_agent` as a fallback.

**Requirements:** Python 3.10+. Works on Windows, macOS, and Linux.

---

## Security

Sol takes security seriously. Every tool category has layered protections:

- **Network** — All outbound requests are checked for SSRF (private IPs, cloud metadata, dangerous schemes are blocked)
- **File system** — Operations are sandboxed to your working directory. Sensitive files (`.ssh`, `.env`, `.aws`) are always blocked
- **Terminal** — Dangerous commands (rm -rf, DROP TABLE, credential access) require your explicit confirmation
- **Browser** — Only http/https URLs. JavaScript eval blocks network requests, cookie access, and eval chains
- **Docker** — Containers run with no network, capped memory/CPU, and no privilege escalation
- **Gateway** — Localhost-only by default. Token auth required when exposed to a network
- **Screen capture** — Window titles are sanitized to prevent command injection

All security validation lives in one file (`security.py`) for easy auditing.

---

## Roadmap

- [x] v0.1 — 72 tools, 4 providers, 21 messaging channels, voice, browser, memory, scheduling, Docker sandbox, multi-agent routing
- [ ] v0.2 — Community skill marketplace, OpenRouter provider, MCP client
- [ ] v0.3 — Local model fine-tuning hooks, agent-to-agent delegation
- [ ] v1.0 — Stable API, comprehensive docs

---

## For Developers

<details>
<summary><b>Architecture</b></summary>

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
        providers/
            openai_provider.py
            anthropic_provider.py
            gemini_provider.py
            ollama_provider.py
    tools/
        file_ops.py          # read, write, edit, patch, grep, find, list, delete
        terminal.py          # Shell execution + background processes
        web.py               # Search + fetch
        blackbox.py          # Autonomous API discovery
        api_registry.py      # API catalog + credential management
        browser.py           # Headless Chrome automation
        voice.py             # ElevenLabs TTS + Whisper STT
        voice_continuous.py  # Always-on mic + wake word + VAD
        screen.py            # Screen capture + annotation
        recording.py         # Screen recording + camera
        docker_sandbox.py    # Isolated container execution
        presence.py          # Notifications + clipboard
        security.py          # SSRF, path sandboxing, input validation
    gateway/
        manager.py           # Channel orchestrator
        channels/            # 21 platform adapters
    cli.py                   # Terminal REPL
    server.py                # Gateway HTTP server
    config.py                # YAML + env var config
```

</details>

<details>
<summary><b>Multi-Agent Routing</b></summary>

Define multiple agents with different personalities, tools, and providers. Route messages by channel, sender, content, or command prefix.

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
    tools:
      enable_browser: false

  research:
    personality:
      name: "Nova"
      role: "research analyst"
      tone: "Thorough, analytical"
      rules:
        - "Always search the web before answering factual questions"

routing:
  strategy: channel
  default: default
  rules:
    discord: coder
    telegram: research
```

</details>

<details>
<summary><b>Custom Tools (Python API)</b></summary>

Add your own tools in a few lines:

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

</details>

<details>
<summary><b>Skills System</b></summary>

Teach Sol new workflows by dropping markdown files into `~/.solstice-agent/skills/`. No code required.

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
```

Three-tier loading keeps token usage minimal — only the skill name is always loaded. Full guides load on-demand.

</details>

<details>
<summary><b>Multimodal (Vision)</b></summary>

Pass images alongside text. Works with all vision-capable providers.

```bash
solstice-agent --image screenshot.png "What's in this image?"
solstice-agent -i design.png -i mockup.png "Compare these designs"
```

</details>

<details>
<summary><b>Context Compaction</b></summary>

Instead of hard-trimming conversation history, Sol summarizes older messages into a compact digest when approaching the model's context window. Long conversations without losing important details.

</details>

<details>
<summary><b>Contributing</b></summary>

PRs welcome. The codebase is intentionally simple — no framework bloat, no over-abstraction.

```bash
git clone https://github.com/Solasticeaistudio/solstice-agent
cd solstice-agent
pip install -e ".[dev,all]"
pytest
```

</details>

---

## License

MIT. Use it, fork it, build on it.

---

Built by [Solstice Studio](https://solsticestudio.ai).
