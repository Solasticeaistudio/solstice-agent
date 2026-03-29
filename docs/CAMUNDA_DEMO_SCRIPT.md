# Camunda Demo Script (Sol)

This script is designed for an automation engineer to validate Camunda 8 workflows end-to-end with Sol.

## 0) Setup (One Time)

```powershell
py -m pip install --upgrade pip pipx
pipx ensurepath
pipx install solstice-agent
pipx inject solstice-agent artemis-camunda
```

> **Important:** use `pipx inject`, not `pip install` — Sol runs in an isolated pipx environment so a regular `pip install artemis-camunda` won't be visible to it.

```powershell
$env:CAMUNDA_BASE_URL="https://your-camunda.example.com"
$env:CAMUNDA_CLIENT_ID="your-client-id"
$env:CAMUNDA_CLIENT_SECRET="your-client-secret"
# Optional — a 14-day trial auto-starts if omitted
$env:ARTEMIS_LICENSE_KEY="your-license-key"

sol --setup
sol
```

If `sol` doesn't launch after install, open a new terminal. If it still fails: `py -m solstice_agent`

## 1) Connect and Validate Cluster

Prompt:

```
Connect to Camunda using my client credentials and show cluster status.
```

Expected: tool call to `camunda_connect` followed by `camunda_status`.

## 2) Deploy a BPMN

Prompt:

```
Deploy the BPMN at C:\path\to\order-approval.bpmn
```

Expected: tool call to `camunda_deploy` with a success response.

## 3) Start a Process Instance

Prompt:

```
Start the process "order-approval" with variables {"orderId": "A-1001", "amount": 1500}
```

Expected: tool call to `camunda_start_process` returning an instance key.

## 4) Query Running Instances

Prompt:

```
Search active process instances for "order-approval".
```

Expected: tool call to `camunda_search_instances`.

## 5) Task Queue (User Tasks)

Prompt:

```
Show open user tasks for assignee "alex".
```

Expected: tool call to `camunda_search_tasks`.

## 6) Complete a Task

Prompt:

```
Complete task 2251799813685249 with variables {"approved": true}.
```

Expected: tool call to `camunda_complete_task`.

## 7) Incident Handling

Prompt:

```
Search incidents for the active process instance and resolve the oldest one.
```

Expected: tool calls to `camunda_search_incidents` and `camunda_resolve_incident`.

## 8) Publish a BPMN Message

Prompt:

```
Publish message "payment_received" with correlation key "A-1001" and variables {"amount": 1500}.
```

Expected: tool call to `camunda_publish_message`.

## 9) Cancel an Instance (Cleanup)

Prompt:

```
Cancel process instance 2251799813685249.
```

Expected: tool call to `camunda_cancel_process`.

---

If any command fails, ask Sol to show the last tool output and confirm credentials.
