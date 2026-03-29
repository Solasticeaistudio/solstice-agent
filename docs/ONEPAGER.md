# Solstice Agent

## The Open-Source AI Agent That Lives On Your Computer

Sol is a local-first AI agent you install on your own machine. It can read files,
use the browser, run commands, remember context, schedule work, and respond across
messaging channels.

No forced cloud account. No fake “agent” layer that is really just chat. This is an
installable product with real tools.

## Core Positioning

- Local-first by default
- Open source and MIT licensed
- Works with OpenAI, Anthropic, Gemini, or Ollama
- Uses real tools on your machine
- Remembers context across sessions
- Can follow you into chat channels while keeping the same memory and identity

## What Makes It Different

Most agent projects sell architecture.

Sol sells ownership.

You install it. It runs on your hardware. It works with your files, your shell, your
browser, and your workflows. The value is not abstract “AI infrastructure.” The value
is that the agent actually lives where your work lives.

## Product Shape

Sol combines:

- a tool-calling agent loop
- persistent cross-session memory
- browser, terminal, file, voice, and scheduling tools
- remote execution: SSH into any server, Singularity/Apptainer for HPC clusters, Modal for serverless GPU workloads
- self-improving skills: synthesizes reusable technique guides from completed tasks, improves them over time
- multi-agent routing
- messaging gateways
- local-first safety guardrails

## Typical Use Cases

- Repo and documentation intelligence
- Dev and ops workflow automation
- API exploration and blackbox discovery
- Personal assistant workflows and recurring tasks
- Founder or operator support across desktop and messaging

## The One-Sentence Pitch

Sol is the open-source AI agent that lives on your computer.

## Quick Install

```powershell
irm https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/Solasticeaistudio/solstice-agent/main/install.sh | bash
```

```bash
sol --setup
sol
```

```bash
pipx install solstice-agent
```

Built by Solstice Studio.
