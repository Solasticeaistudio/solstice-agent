# Solstice Site Copy

This file is the site-ready copy deck for `solsticestudio.ai/sol`.

## Hero

### Headline
The open-source AI agent that lives on your computer.

### Subhead
Talk to it. It reads files, uses the browser, runs commands, remembers context, and works across your apps.

### Support line
No forced cloud account. Your machine. Your data. Your agent.

### Primary CTA
Install Sol

### Secondary CTA
View GitHub

## Hero Install Block

### Windows
```powershell
irm https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.ps1 | iex
```

### macOS / Linux
```bash
curl -fsSL https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.sh | bash
```

### pipx
```bash
pipx install solstice-agent
```

### Quick Start
```bash
sol --setup
sol
```

## Hero Proof Bar

- Open source
- Local-first
- MIT licensed
- Runs on normal hardware

## Section: What It Feels Like

### Header
It feels like an agent, not a chatbot wrapper.

### Body
Sol lives where your work lives: your files, your terminal, your browser, your notifications, and your chats. You install it once, then talk to it like it is part of your machine.

### Prompt examples

```text
Summarize this repo and tell me how it works
Check my calendar every morning and message me the summary
Inspect this API and figure out what auth it uses
Remember that I deploy production on Fridays
Hey Sol, what's on my screen?
Draft an investor follow-up and attach the deck
```

## Section: Why Sol

### Header
Why people care

### Bullets
- Runs on normal computers
- Local-first by default
- Open source and MIT licensed
- Works with OpenAI, Anthropic, Gemini, or Ollama
- Uses real tools instead of pretending
- Same agent across desktop and messaging channels

## Section: What It Can Do

### Header
Real tools. Real work.

### Cards
- Files
  Read, write, patch, and search files on your machine.
- Browser
  Search, open, click, type, and inspect real pages.
- Terminal
  Run commands, inspect logs, and automate repeatable workflows.
- API Discovery
  Point Sol at an API and let it map the surface area.
- Memory
  Keep facts and conversation context across sessions.
- Scheduling
  Run recurring work while you are away.
- Remote Execution
  SSH into any server. Run commands, transfer files, and manage sessions without leaving the agent.
- HPC Containers
  Run Singularity and Apptainer workloads on HPC clusters where Docker is unavailable or requires root.
- Serverless
  Offload heavy compute to Modal. GPU jobs, persistent apps, scheduled runs — no infrastructure to manage.
- Self-Improving Skills
  Sol synthesizes reusable technique guides from completed tasks and improves them over time. The more you use it, the better it gets.

## Section: Local-First

### Header
Use cloud models if you want. Stay local if you want.

### Body
Sol works with OpenAI, Anthropic, Gemini, or Ollama. You are not locked to one provider, one model, or one hosted account.

## Section: Installation Confidence

### Header
Installable, not aspirational

### Body
Sol ships as the `solstice-agent` package and installs the `sol` command. The install path is tested in CI as a packaged CLI, not just as an editable repo checkout.

## Section: Security

### Header
Power with guardrails

### Body
Sol is intentionally capable, so the safety story matters. Network requests are checked for SSRF, file access is sandboxed, dangerous terminal actions require confirmation, and gateway access is locked down by default.

## Section: CTA

### Header
Install your own agent

### Body
No signup wall. No waitlist theater. Just install it and make it useful.

### CTA
Get Started
