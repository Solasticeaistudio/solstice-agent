Subject: Sol + Camunda quick test (Windows)

Hey [Name],

Here's a quick path to test Sol with Camunda on Windows.

1) Install Sol + the Camunda connector
```powershell
py -m pip install --upgrade pip pipx
pipx ensurepath
pipx install solstice-agent
pipx inject solstice-agent artemis-camunda
```

Note: use `pipx inject`, not `pip install` — Sol runs in an isolated pipx environment so a regular `pip install artemis-camunda` won't be visible to it.

2) Set your Camunda creds
```powershell
$env:CAMUNDA_BASE_URL="https://your-camunda.example.com"
$env:CAMUNDA_CLIENT_ID="your-client-id"
$env:CAMUNDA_CLIENT_SECRET="your-client-secret"
# Optional license key (trial auto-starts if omitted)
$env:ARTEMIS_LICENSE_KEY="your-license-key"
```

3) Run Sol
```powershell
sol --setup
sol
```

If `sol` doesn’t launch, open a new terminal. If it still fails, use:
```powershell
py -m solstice_agent
```

4) Demo prompts to validate Camunda end-to-end:
- Connect to Camunda using my client credentials and show cluster status.
- Deploy the BPMN at `C:\path\to\order-approval.bpmn`
- Start the process `order-approval` with variables `{"orderId": "A-1001", "amount": 1500}`
- Search active process instances for `order-approval`.
- Show open user tasks for assignee `alex`.
- Complete task `2251799813685249` with variables `{"approved": true}`.
- Search incidents for the active process instance and resolve the oldest one.
- Publish message `payment_received` with correlation key `A-1001` and variables `{"amount": 1500}`.

If you hit any issues, send me the terminal output and I’ll fix it fast.

Thanks!
