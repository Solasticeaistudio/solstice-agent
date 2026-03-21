# Security

Sol is intentionally capable, so the trust boundary needs to be explicit.

## Runtime Profiles

Sol resolves tool defaults from one of four runtime profiles:

- `local_safe`: local CLI defaults with terminal, web fetch/search, memory, scheduler, skills, and registry enabled
- `developer`: broader local workflow profile that also enables browser, blackbox, and Docker tooling
- `gateway`: safe remote-facing defaults for messaging/server deployments
- `power_user`: broad capability surface, including opt-in desktop and outreach features

CLI defaults to `developer`.

Gateway/server defaults to `gateway`.

You can override the profile with `--profile` or `runtime_profile` in config, then override individual tool flags explicitly if needed.

## Filesystem Policy

- File operations are always checked against the shared path policy in `solstice_agent/tools/security.py`
- Sensitive paths such as `.ssh`, `.gnupg`, `.aws/credentials`, `.env`, and Docker auth files are blocked
- Gateway file access fails closed unless `workspace_root` is configured
- CLI file access defaults to the configured `workspace_root`, or the current working directory if none is set

## Network Policy

- `fetch_url` validates URLs before requests and validates redirect targets before following them
- `browser_navigate` uses the same URL policy as fetch, including private-address and metadata-endpoint blocking
- Private IP space, localhost, link-local ranges, and common metadata endpoints are blocked by default

## Command Safety

- Dangerous terminal commands require confirmation through the command safety layer
- Gateway deployments should keep terminal access disabled unless there is a deliberate reason to expose it
- Docker sandbox tasks run with `no-new-privileges` and without network access

## Gateway Mode

Gateway mode is meant to be the conservative remote-facing posture:

- no terminal by default
- no web by default
- no browser, screen, recording, presence, voice, Docker, or outreach by default
- file tools only inside the configured workspace root
- localhost bind by default, token required when exposed beyond localhost

Example:

```bash
sol-gateway --profile gateway --workspace-root /absolute/path/to/workspace
```

## Provider Packaging

Provider SDKs are optional extras:

- `solstice-agent[openai]`
- `solstice-agent[anthropic]`
- `solstice-agent[gemini]`

The base package works well with Ollama and local tooling. If you select a cloud provider without its extra installed, Sol should return an install hint instead of failing silently.
