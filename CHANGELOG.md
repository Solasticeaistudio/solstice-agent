# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-21

### Added

#### Core Agent
- Interactive CLI with REPL mode, one-shot messaging, and session resumption
- 4 LLM providers: OpenAI (GPT-4o), Anthropic (Claude), Google Gemini, Ollama (local)
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
