<p align="center">
  <img src="assets/solstice-logo.png" alt="Sol" width="180">
</p>

<h1 align="center">Sol</h1>

<p align="center">The open-source AI agent that lives on your computer.</p>

<p align="center">
  Talk to it. It reads files, uses the browser, runs commands, remembers context,
  and works across your apps.
</p>

<p align="center">
  No forced cloud account. Your machine. Your data. Your agent.
</p>

<p align="center">
  <a href="https://pypi.org/project/solstice-agent/"><img src="https://img.shields.io/pypi/v/solstice-agent?color=8b5cf6&style=flat-square" alt="PyPI"></a>
  <a href="https://pypi.org/project/solstice-agent/"><img src="https://img.shields.io/pypi/pyversions/solstice-agent?color=70e1ff&style=flat-square" alt="Python"></a>
  <a href="https://github.com/Solasticeaistudio/solstice-agent/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Solasticeaistudio/solstice-agent?color=10b981&style=flat-square" alt="License"></a>
  <a href="https://github.com/Solasticeaistudio/solstice-agent/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Solasticeaistudio/solstice-agent/ci.yml?style=flat-square&label=CI" alt="CI"></a>
  <img src="https://img.shields.io/badge/local--first-yes-0ea5e9?style=flat-square" alt="Local First">
  <img src="https://img.shields.io/badge/open%20source-MIT-64748b?style=flat-square" alt="Open Source">
</p>

---

## Quick Install

Pick the provider path you actually want:

**Base package + Ollama**:
```bash
pipx install solstice-agent
```

**OpenAI**:
```bash
pipx install 'solstice-agent[openai]'
```

**Anthropic**:
```bash
pipx install 'solstice-agent[anthropic]'
```

**Gemini**:
```bash
pipx install 'solstice-agent[gemini]'
```

If you want the one-line installers, they install the OpenAI extra by default.

**Windows** (PowerShell):
```powershell
irm https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.ps1 | iex
```

**macOS / Linux**:
```bash
curl -fsSL https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.sh | bash
```

Then:

```bash
sol --setup
sol
```

For gateway deployments, set an explicit workspace root:

```bash
sol-gateway --profile gateway --workspace-root /absolute/path/to/workspace
```

Legacy aliases still work:

```bash
solstice-agent
solstice-gateway
```

## What It Feels Like

```text
> Summarize this repo and tell me how it works
> Check my calendar every morning and message me the summary
> Open this API and figure out what auth it uses
> Remember that I deploy production on Fridays
> Hey Sol, what's on my screen?
```

Sol is not a chatbot wrapper. It is an installable agent with real tools, persistent
memory, voice, scheduling, browser control, and local-first guardrails.

## Why Sol

- Runs on normal computers
- Open source and MIT licensed
- Local-first by default
- Works with OpenAI, Anthropic, Gemini, or Ollama when the matching provider path is installed
- Uses real tools instead of pretending
- Same agent across terminal, desktop, and messaging channels

## What It Can Do

Sol ships with built-in tools across files, browser, terminal, web, API discovery,
voice, screen capture, recording, Docker sandboxing, SSH remote execution,
Singularity/Apptainer HPC containers, Modal serverless compute, scheduling,
self-improving skills, memory, and cross-channel messaging.

It also supports external connectors installed into the same Python environment.
That interface stays public, while deep Artemis integrations can ship as separate
packages. Connector loading and boundary details live in `docs/CONNECTORS.md`.

What that means in practice:

- Read, write, patch, and search files on your machine
- Run commands, background jobs, and inspect logs
- Search the web and open pages in a real browser
- Inspect unfamiliar APIs and map their endpoints
- SSH into remote servers and run commands, transfer files, manage sessions
- Run Singularity/Apptainer containers on HPC clusters where Docker isn't an option
- Offload heavy compute to Modal — ephemeral GPU jobs or persistent scheduled apps
- Remember facts and resume conversations across sessions
- Synthesize reusable skill guides from completed tasks and improve them over time
- Listen for a wake word and reply by voice
- Schedule recurring work while you are away
- Respond through messaging platforms using the same memory and personality

## The Main Hook

Most agent projects feel like hosted wrappers around an LLM.

Sol feels different because it lives where your work lives:

- your filesystem
- your terminal
- your browser
- your notifications
- your chats

That is the product.

## Local-First by Default

Sol can run with:

- OpenAI
- Anthropic
- Gemini
- Ollama for fully local inference

Use cloud models if you want. Use local models if you want. The product is not tied
to one provider or one hosted account.

```bash
# OpenAI
export OPENAI_API_KEY=sk-...
sol

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
sol --provider anthropic

# Google Gemini
export GEMINI_API_KEY=AI...
sol --provider gemini

# Ollama (fully local)
sol --provider ollama --model llama3.1
```

## Reach It From Anywhere

Sol can expose the same agent across messaging channels. Message it on Telegram,
Discord, Slack, email, or other supported gateways and keep the same memory and
personality.

Example:

```bash
export GATEWAY_TELEGRAM_ENABLED=true
export GATEWAY_TELEGRAM_BOT_TOKEN=your-token
sol-gateway
```

For Outlook/Graph email channels, Sol can use either a direct `GATEWAY_EMAIL_GRAPH_TOKEN`
or a shared MSAL cache file via `GATEWAY_EMAIL_GRAPH_CACHE_PATH`.

## Talk to It by Voice

Say "hey Sol" and start talking. Sol can listen through your microphone, maintain a
live transcript, and respond out loud. You can also switch voices, use push-to-talk,
or disable voice entirely.

## It Remembers

Sol stores conversation history and facts across sessions.

```bash
sol --continue
```

Example:

```text
> Remember that my preferred language is Python
> What's my preferred language?
Python.
```

## Schedule Work

Sol can run recurring tasks even when you are not actively chatting with it.

```bash
sol --cron "every day at 9am" "summarize my calendar"
```

You can also just ask:

```text
> Schedule a daily summary of my GitHub notifications at 9am
```

## Docs

- Security: `docs/SECURITY.md`
- Connectors: `docs/CONNECTORS.md`
- Camunda quickstart: `docs/WINDOWS_CAMUNDA_QUICKSTART.md`
- Camunda demo script: `docs/CAMUNDA_DEMO_SCRIPT.md`

## Install Options

If you prefer the cleanest CLI install:

```bash
pipx install solstice-agent
```

Provider extras:

```bash
pipx install 'solstice-agent[openai]'
pipx install 'solstice-agent[anthropic]'
pipx install 'solstice-agent[gemini]'
```

If you prefer manual install:

```bash
pip install 'solstice-agent[all]'
```

Or install only what you need:

```bash
pip install solstice-agent
pip install 'solstice-agent[openai]'
pip install 'solstice-agent[anthropic]'
pip install 'solstice-agent[gemini]'
pip install 'solstice-agent[voice]'
pip install 'solstice-agent[browser]'
pip install 'solstice-agent[gateway]'
pip install 'solstice-agent[screen]'
pip install 'solstice-agent[recording]'
pip install 'solstice-agent[docker]'
```

Browser support requires:

```bash
playwright install chromium
```

## Security

Sol is intentionally powerful, so the safety story matters.

- Runtime profiles make tool defaults explicit: `local_safe`, `developer`, `gateway`, `power_user`
- Network requests are checked for SSRF and blocked from private/internal targets
- Gateway file operations fail closed unless `workspace_root` is configured
- File operations are sandboxed to the workspace and sensitive paths are blocked
- Dangerous terminal commands require explicit confirmation
- Browser execution is constrained
- Docker sandbox jobs run without network and without privilege escalation
- Gateway server binds to localhost by default and uses token auth when exposed

Security validation is centralized in `solstice_agent/tools/security.py` for auditing.

Dedicated security guide: `docs/SECURITY.md`

## Architecture

```text
solstice_agent/
  agent/
    core.py
    memory.py
    scheduler.py
    router.py
    providers/
  tools/
    file_ops.py
    terminal.py
    web.py
    blackbox.py
    browser.py
    voice.py
    screen.py
    recording.py
    docker_sandbox.py
    security.py
  gateway/
    manager.py
    channels/
  cli.py
  server.py
```

At the center is a tool-calling loop. User message in, model decides whether to use
tools, tools execute, results come back, final answer returns.

## Roadmap

- Community skill marketplace
- OpenRouter provider
- MCP client support
- Agent-to-agent delegation
- Stable public API

## Contributing

```bash
git clone https://github.com/Solasticeaistudio/solstice-agent
cd solstice-agent
pip install -e ".[dev,all]"
pytest
```

## License

MIT.

Built by [Solstice Studio](https://solsticestudio.ai).
