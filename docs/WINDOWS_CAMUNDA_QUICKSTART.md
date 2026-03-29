# Windows + Camunda Quickstart

This is the simplest way to get Sol running on Windows and connected to Camunda.

## 1) Install Sol

Open PowerShell and run:

```powershell
py -m pip install --upgrade pip pipx
pipx ensurepath
pipx install solstice-agent
```

If `sol` does not launch after install, open a new terminal first. If it still fails, use the module entrypoint:

```powershell
py -m solstice_agent --setup
py -m solstice_agent
```

If the CLI works, you can use:

```powershell
sol --setup
sol
```

## 2) Install the Camunda Connector

```powershell
pipx inject solstice-agent artemis-camunda
```

This installs the connector into the same isolated environment as `sol`, which is required for connector auto-discovery. **Do not use `pip install artemis-camunda`** — Sol won't see it because pipx isolates its environment from the system Python.

## 3) Set Camunda Environment Variables

Set these in PowerShell:

```powershell
$env:CAMUNDA_BASE_URL="https://your-camunda.example.com"
$env:CAMUNDA_CLIENT_ID="your-client-id"
$env:CAMUNDA_CLIENT_SECRET="your-client-secret"
```

If your connector uses different variable names, update them here.

## 4) Artemis License (Optional)

The Camunda connector supports a local-only trial and license system.
By default it auto-starts a 14-day trial on first use.

If you have a license key, set:

```powershell
$env:ARTEMIS_LICENSE_KEY="your-license-key"
```

## 5) Run Sol

```powershell
sol
```

If the CLI entrypoint fails:

```powershell
py -m solstice_agent
```

## 6) Test the Camunda Connector

Example prompts:

- `Connect to Camunda using my client credentials and show cluster status.`
- `List available Camunda clusters and endpoints.`
- `Show me deployed workflows.`
- `Start a workflow instance for process "order-approval".`

## Troubleshooting

### If `sol` does nothing

Run:

```powershell
sol --help
```

If that fails but this works:

```powershell
py -m solstice_agent --help
```

then your PATH or shell session is stale.

### Find the Python location

```powershell
py -c "import sys; print(sys.executable)"
```

If needed, restart PowerShell after `pipx ensurepath`.

---

If you want this wired into a dedicated Camunda demo, use `docs/CAMUNDA_DEMO_SCRIPT.md`.
