# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.11] - 2026-04-01

### Added
- Shared onboarding helpers so CLI and gateway quick-start flows stay aligned
- Guided `/start` onboarding for gateway and webchat, including first-reply interpretation after the menu is shown

### Changed
- Provider credentials from environment variables now fill the selected provider instead of silently switching providers
- Setup wizard uses simpler, plain-English provider and runtime choices with starter prompts at the end
- CLI first-run flow is safer by default, auto-starts with guided onboarding, and understands broader natural-language onboarding phrases
- Gateway onboarding now recognizes broader everyday language around files, reminders, calendars, email, notes, and messages

## [0.2.10] - 2026-04-01

### Added
- Persistent sub-agent orchestration with async runs, task tracking, workflow DAGs, workflow mutation, branch retry, workflow snapshots, and JSON export
- Workflow-level streaming and follow surfaces across CLI, gateway, and server endpoints
- New user guide and roadmap/todo documentation for orchestration workflows

### Changed
- README now documents workflow orchestration as a first-class capability
- CLI, gateway, and server surfaces expose workflow mutation, inspection, snapshot, and export operations

## [0.2.6] - 2026-03-29

### Added
- **SSH remote execution** — `ssh_connect`, `ssh_exec`, `ssh_disconnect`, `ssh_list`, `ssh_upload`, `ssh_download`; persistent sessions via paramiko, SFTP file transfer, thread-safe connection pool (max 10 sessions)
- **Singularity / Apptainer sandbox** — HPC container execution (`singularity_run`, `singularity_run_async`, `singularity_status`, `singularity_list`, `singularity_pull`); works on clusters where Docker requires root; auto-detects apptainer vs singularity binary
- **Modal serverless sandbox** — `modal_run` (ephemeral GPU/CPU jobs), `modal_deploy` (persistent apps with optional cron), `modal_list`, `modal_stop`; generates self-contained app scripts on the fly
- **Self-improving skill system** — `SkillSynthesizer` class + `skill_save` / `skill_improve` tools; after complex tasks (≥4 tool calls), Sol automatically prompts the LLM to decide if a reusable skill guide should be saved or updated; skills stored in `~/.solstice-agent/skills/synthesized/` and hot-reloaded immediately
- New `synthesizer=` parameter on `Agent` — pass a `SkillSynthesizer` to enable the learning loop; threshold is configurable
- New `[ssh]` and `[modal]` package extras

### Changed
- `Agent.chat()` now counts tool invocations per task and passes the total to the synthesizer post-response
- `ToolRegistry.load_builtins()` gains four new flags: `enable_ssh`, `enable_singularity`, `enable_modal`, `enable_synthesis` (all `True` by default)
- Total built-in tools: **89** (up from 72)

## [0.2.4] - 2026-03-15

### Added
- Primary `sol`, `sol-gateway`, and `sol-tray` CLI aliases while preserving the legacy `solstice-*` commands
- Draft-first Outlook/Graph outreach flow with approved-attachment support for investor and partner campaigns
- Campaign knowledge-base loading and an IRIS-style investor outreach persona
- Dedicated install smoke-test coverage for packaged CLI entrypoints

### Changed
- Installers and README now lead with the `sol` command instead of `solstice-agent`
- Release messaging and site copy now align package name (`solstice-agent`) with product name (`Sol`)

## [0.2.2] - 2026-02-27

### Changed
- All optional dependencies (LLM providers, voice, browser, screen, docker, gateway, tray) are now included in the base install — `pip install solstice-agent` gives you the full toolkit out of the box
- Individual extras (`[openai]`, `[voice]`, `[browser]`, etc.) still available for minimal installs

### Fixed
- Cleaned up corrupted dist-info leftovers that could cause install conflicts when upgrading from v0.1.x

## [0.1.0] - 2026-02-21

### Added

#### Core Agent
- Interactive CLI with REPL mode, one-shot messaging, and session resumption
- 4 LLM providers: OpenAI, Anthropic, Google Gemini, Ollama (local)
- Multimodal image input support across all vision-capable providers
- LLM-based context compaction (summarization, not hard truncation)
- Persistent cross-session memory (JSON-backed)
- Multi-agent routing with per-agent tool sets and personalities
- 3-tier skills system (markdown-based, token-efficient)
- Persistent cron scheduling for background tasks
- Interactive setup wizard (`--setup`)
- 5 built-in personalities: assistant, engineer, researcher, creative, minimal

#### Tools (72 total)
- **File Operations** (8): read, write, edit, patch, list, delete, grep, find
- **Terminal** (6): run commands, background processes with status/log/write/kill
- **Web** (2): DuckDuckGo search, URL fetching
- **Blackbox API Discovery** (6): connect, discover, fingerprint, spider, pull, push
- **API Registry** (6): search, add, get, connect, stats, remove — 25 pre-seeded APIs
- **Browser Automation** (7): navigate, read, click, type, screenshot, eval, close (Playwright)
- **Voice** (3): ElevenLabs TTS, Whisper STT, voice listing
- **Continuous Voice** (4): start/stop listening, status, wake word configuration
- **Persistent Memory** (4): remember, recall, forget, list conversations
- **Skills** (2): get, list
- **Screen Capture** (4): full screen, window, list displays, annotate
- **Docker Sandbox** (7): run, start, exec, stop, list, copy in/out
- **Presence** (4): notifications, status, clipboard get/set
- **Recording** (5): start/stop recording, status, camera capture/list
- **Scheduling** (3): cron add, list, remove

#### Messaging Gateway (21 channels)
- WhatsApp, Telegram, Discord, Slack, Email (IMAP+SMTP)
- Microsoft Teams, iMessage (BlueBubbles), Signal (signal-cli)
- Matrix, Google Chat, IRC, Mattermost, LINE
- Twitch, Facebook Messenger, Twitter/X, Reddit
- Nostr (NIP-04), WebChat, Feishu/Lark, Generic Webhook
- Flask-based gateway server with bearer token auth
- Per-sender conversation isolation and multi-agent routing

#### Security (9 layers)
- SSRF protection (private IPs, cloud metadata, dangerous schemes)
- Path sandboxing with symlink resolution
- Sensitive file blocklist (.ssh, .aws, .env, .gnupg)
- Dangerous command detection (40+ patterns)
- Browser URL scheme allowlist and JS eval restrictions
- Docker container isolation (no network, memory/CPU limits, no privilege escalation)
- Window title sanitization
- Gateway localhost-only by default with token auth
- Centralized security module for auditability

#### Packaging
- `pip install solstice-agent` with modular optional dependencies
- Entry points: `solstice-agent`, `solstice-gateway`, `solstice-tray`
- CI: GitHub Actions on Ubuntu/Windows/macOS, Python 3.10-3.13
- 310 tests passing, ruff lint clean
