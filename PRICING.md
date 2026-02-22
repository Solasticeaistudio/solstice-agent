# Solstice Agent — Pricing & Release Strategy

> **Competitor:** OpenClaw (formerly Clawdbot/Moltbot) — 140k GitHub stars, creator acqui-hired by OpenAI (Feb 15, 2026).
> **Window:** OpenClaw is semi-orphaned. OpenAI hasn't shipped their hosted agent product yet. 3-6 month land-grab window.
> **Strategy:** Sol is the open-source trojan horse. Iris is the product. Don't give Iris away.

---

## The Play

```
Sol (free, open source)          Iris (paid, premium)
├─ 72 tools                      ├─ Everything in Sol, plus:
├─ 21 messaging channels         ├─ Glassmorphism sci-fi desktop app
├─ 4 LLM providers + Ollama      ├─ 3D avatar (Baymax/Chibi) with state animations
├─ CLI + system tray              ├─ Voice assistant (wake word, VAD, duplex audio)
├─ Persistent memory              ├─ Gesture recognition (MediaPipe, 14 gestures)
├─ Docker sandboxing              ├─ Screen annotations (grid system, overlays)
├─ Browser automation             ├─ Visual canvas (code preview, Mermaid diagrams)
├─ Cron scheduling                ├─ Workspace snapshots & war room layouts
├─ Skills system                  ├─ Proactive intelligence (JARVIS-style alerts)
└─ Gateway server                 ├─ Macro engine (30+ action types)
                                  ├─ Companion server (mobile sync)
                                  └─ Cloud relay (remote control)

Sol competes with OpenClaw.
Iris has no competition.
```

---

## Tier 1: Sol — Community Edition (Free)

* **Price:** Free forever (MIT License)
* **Product:** `solstice-agent` — CLI agent + messaging gateway
* **Target:** Developers, tinkerers, OpenClaw migrants, self-hosters.
* **Goal:** Maximum adoption. Build the community. Prove the framework. Funnel to Iris.
* **Features:**
  * Full 72-tool suite — no feature gating
  * All 4 LLM providers (OpenAI, Anthropic, Gemini, Ollama) — BYOK
  * All 21 messaging channels (you bring API keys + host the server)
  * Local persistent memory (JSON)
  * Unlimited local cron jobs
  * Docker sandboxing (local)
  * Browser automation (Playwright)
  * CLI REPL + system tray
  * Voice tools (ElevenLabs TTS + Whisper STT) — BYOK, terminal-only
  * Skills system + multi-agent routing
  * Connect your own Vector DB with your own keys

**What Sol is NOT:** Sol is not Iris. No desktop app, no avatar, no gesture control, no visual canvas, no screen annotations. Sol is the engine. Iris is the cockpit.

---

## Tier 2: Iris — Desktop Pro

* **Price:** $29/month ($249/year)
* **Product:** `iris-desktop` — Tauri + React desktop application
* **Target:** Power users, founders, executives, creators who want a visual AI operating system.
* **Goal:** Primary revenue driver. The thing nobody else has.
* **Features:**
  * **Everything in Sol** (full tool suite, all providers, all channels)
  * **Glassmorphism Desktop App:** Tauri-native, frameless, transparent, always-on-top. Sci-fi UI with animated backlights (cyan/gold/violet/rainbow state glow).
  * **3D Avatar:** Three.js Baymax/Chibi with state-driven animations, audio-reactive mouth, emotion mapping.
  * **Voice Assistant:** Wake word detection, VAD, full duplex audio, native Rust audio capture, streaming TTS. Hands-free operation.
  * **Gesture Recognition:** MediaPipe face/hand detection, 14 gesture types, 20 action bindings, 4 preset modes (focus, gaming, creative, presentation).
  * **Screen Annotations:** Draw circles, arrows, highlights, text overlays. Grid-based coordinate system with resolution calibration.
  * **Visual Canvas:** Code preview window, Mermaid diagram rendering, chart visualization.
  * **Workspace Management:** Snapshot/restore window layouts, war room multi-monitor presets.
  * **Proactive Intelligence:** Battery monitoring, idle detection, pattern recognition, meeting reminders, custom triggers.
  * **Macro Engine:** 30+ action types, YAML-based triggers, keyboard/mouse automation.
  * **System Integration:** Window management, media control, brightness, WiFi/BT toggle, app launching.
  * **Companion Server:** WebSocket on port 9999 for mobile app sync.
  * **Cloud Relay:** Remote control via solstice.solsticestudio.ai.

**Why $29?** There is nothing like Iris on the market. OpenClaw is terminal-only. Cursor is a code editor. Iris is a visual AI operating system with a 3D avatar, voice control, and gesture recognition. $29 is a steal.

---

## Tier 3: Iris Cloud

* **Price:** $49/month ($449/year)
* **Target:** Users who want Iris + 24/7 always-on agent hosting.
* **Goal:** High-value upsell. Iris Desktop + cloud infrastructure.
* **Features:**
  * **Everything in Iris Desktop**
  * **1-Click 24/7 Hosting:** Upload config → we host your agent. Always on, even when your laptop is closed.
  * **Managed Webhooks:** Static, reliable endpoints for all 21 channels (no ngrok).
  * **Unified API Key:** One `SOLSTICE_API_KEY` for Twilio, SendGrid, ElevenLabs, Maps, Weather, and more. Consolidated billing.
  * **Cloud Memory Sync:** Agent memory synced across Iris Desktop + hosted instance, encrypted at rest.
  * **Managed Vector DB:** Pinecone namespace provisioned and managed — infinite RAG memory, zero setup.
  * **Web Dashboard:** Conversation history, cron monitoring, telemetry, usage analytics.

### Usage Caps (included in $49/mo)
| Resource | Included | Overage |
|---|---|---|
| Gateway messages | 10,000/mo | $0.002/msg |
| Agent uptime | 24/7 (1 agent) | $9/mo per additional agent |
| Unified API passthrough | Billed at cost + 15% | — |
| Cloud memory storage | 1 GB | $2/GB/mo |
| Vector DB records | 100k vectors | $5 per 100k/mo |

---

## Tier 4: Team

* **Price:** $49/user/month (minimum 3 users)
* **Target:** Agencies, startups, small companies running multiple agents.
* **Features:**
  * Everything in Iris Cloud
  * Multi-agent RBAC (role-based access control)
  * Shared memory across agents
  * Team dashboard with per-agent analytics
  * Audit logs
  * 3 hosted agents included (additional $9/mo each)

---

## Tier 5: Enterprise

* **Price:** Custom
* **Target:** Larger companies integrating Solstice into core operations.
* **Features:**
  * SOC2 compliance
  * VPC peering & dedicated IPs
  * Custom SLA & priority support
  * Dedicated infrastructure
  * SSO/SAML integration
  * Unlimited agents
  * On-premise Iris deployment

**Don't invest here until Iris Cloud has traction.**

---

## The Funnel

```
GitHub / PyPI / HN / Reddit / Twitter
            │
            ▼
    Sol (free, open source)         ← Compete with OpenClaw here
    "Wow, this is better than OpenClaw"
            │
            ▼
    Iris Desktop ($29/mo)           ← No competition here
    "Holy shit, it has a 3D avatar and gesture control"
            │
            ▼
    Iris Cloud ($49/mo)             ← Lock-in here
    "I need this running 24/7 on my Telegram"
            │
            ▼
    Team / Enterprise               ← Scale here
```

---

## What Goes Where

| Feature | Sol (Free) | Iris ($29) | Cloud ($49) |
|---|---|---|---|
| 72 tools | Yes | Yes | Yes |
| 21 channels | Yes (BYOK) | Yes (BYOK) | Yes (managed) |
| 4 LLM providers | Yes | Yes | Yes |
| CLI + tray | Yes | Yes | Yes |
| Desktop app | No | Yes | Yes |
| 3D avatar | No | Yes | Yes |
| Voice assistant | Terminal only | Full (wake word, VAD, duplex) | Full |
| Gesture control | No | Yes | Yes |
| Screen annotations | No | Yes | Yes |
| Visual canvas | No | Yes | Yes |
| Proactive intelligence | No | Yes | Yes |
| Macro engine | No | Yes | Yes |
| 24/7 hosting | No | No | Yes |
| Managed webhooks | No | No | Yes |
| Unified API key | No | No | Yes |
| Cloud memory sync | No | No | Yes |
| Web dashboard | No | No | Yes |

---

## Competitive Positioning

| | OpenClaw | Sol (Free) | Iris (Paid) |
|---|---|---|---|
| Core agent | Free | Free | $29/mo |
| Desktop app | None | System tray only | Full sci-fi UI |
| 3D avatar | No | No | Yes (Three.js) |
| Voice | Basic | Terminal TTS/STT | Wake word + VAD + duplex |
| Gestures | No | No | Yes (MediaPipe) |
| Screen annotations | No | No | Yes |
| Hosted option | No | No | $49/mo (Iris Cloud) |
| Channels | ~5 | 21 | 21 (managed) |
| Tools | ~30 | 72 | 72 + visual tools |
| Active maintainer | Left for OpenAI | Yes | Yes |

**Marketing angles:**

Sol vs OpenClaw:
> *"Everything OpenClaw does, with twice the tools, four times the channels, and someone who's actually still working on it."*

Iris vs everything:
> *"You've been typing commands into a terminal like it's 1985. Meet Iris."*
