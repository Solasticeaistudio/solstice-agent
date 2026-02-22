# Sol vs OpenClaw — Side by Side

|                      | OpenClaw                          | Sol (Solstice Agent)                    |
|----------------------|-----------------------------------|-----------------------------------------|
| **Tools**            | ~25 (file access, scripts)        | **72** built-in                         |
| **Codebase**         | ~430K lines                       | **~12K lines** — 35x less code          |
| **Install**          | Docker required                   | `pip install solstice-agent`            |
| **Providers**        | Primarily OpenAI                  | OpenAI, Anthropic, Gemini, Ollama       |
| **Security**         | CVE-2026-25253 RCE, 30K exposed   | 9 security layers, 0 CVEs              |
|                      | instances, 20% malicious skills   | Audited *before* launch                 |
| **Path Sandboxing**  | No                                | Yes — workspace boundary enforcement    |
| **SSRF Protection**  | No                                | Yes — blocks private IPs, metadata      |
| **Command Injection**| Vulnerable                        | Blocked — 40+ dangerous patterns        |
| **Container Isolation**| Runs IN Docker                  | Runs Docker — sandboxes untrusted code  |
| **Gateway Auth**     | None                              | Bearer token + localhost-only default   |
| **API Discovery**    | Write a skill per API             | Autonomous — point at any URL           |
| **Browser**          | Sandboxed automation              | Full Playwright (nav, click, eval, etc) |
| **Voice**            | ElevenLabs TTS only               | TTS + STT + wake word + continuous mic  |
| **Screen Capture**   | No                                | Yes — capture, annotate, record         |
| **Memory**           | Markdown files                    | Persistent JSON — facts + conversations |
| **Multi-agent**      | Workspace isolation               | Config-driven routing per agent         |
| **Context Mgmt**     | Hard trim at 128K                 | LLM-summarized compaction               |
| **Vision**           | Not built-in                      | Native multimodal — all providers       |

> *Sol is the open-source core of Iris → solsticestudio.ai/iris*
