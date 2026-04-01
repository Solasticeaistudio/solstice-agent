# User Guide

This guide covers the main ways to use Sol from the terminal and the new workflow orchestration surface.

## First Run

Install Sol and configure a provider:

```bash
pipx install solstice-agent
sol --setup
sol
```

You can also select a provider directly:

```bash
sol --provider openai
sol --provider anthropic
sol --provider gemini
sol --provider ollama --model llama3.1
```

## Basic CLI Usage

Interactive mode:

```bash
sol
```

One-shot mode:

```bash
sol "Summarize this repository and identify risky areas"
```

Resume the previous conversation:

```bash
sol --continue
```

## Core Capabilities

Sol can:

- read, write, patch, and search files
- run shell commands and inspect logs
- browse the web and control a browser
- remember facts across sessions
- schedule recurring work
- operate through gateway channels
- delegate background work to sub-agents
- run workflow DAGs with dependency tracking and snapshots

## Tasks

Show tracked tasks:

```bash
sol --tasks
```

Clear tracked tasks:

```bash
sol --clear-tasks
```

In interactive mode:

```text
/tasks
/clear-tasks
```

## Sub-Agents

Sub-agents are focused child runs that can execute in the background with progress tracking and persistence.

Useful commands:

```text
/subagents
/subagent <run_id>
/subagent-progress <run_id>
/resume-subagent <run_id>
/cancel-subagent <run_id>
/subagent-graph
```

Non-interactive inspection:

```bash
sol --subagents
sol --subagent-result <run_id>
sol --subagent-progress <run_id>
sol --resume-subagent <run_id>
sol --cancel-subagent <run_id>
```

## Workflows

Workflows are DAGs of sub-agent runs with dependency policies, retries, priorities, event streams, and persistent state.

List workflows:

```bash
sol --workflows
```

Inspect one workflow:

```bash
sol --workflow-status <workflow_id>
sol --workflow-events <workflow_id>
```

Interactive equivalents:

```text
/workflows
/workflow <workflow_id>
/workflow-events <workflow_id>
```

### Mutating a Workflow

Add a node:

```text
/add-workflow-node <workflow_id> <node_id> <prompt>
```

Retry a node or branch:

```text
/retry-workflow-node <workflow_id> <node_id>
/retry-workflow-branch <workflow_id> <node_id>
```

Adjust scheduling and dependency policy:

```text
/set-workflow-priority <workflow_id> <node_id> <priority>
/set-workflow-edge <workflow_id> <node_id> <dependency_node_id> <policy>
/rewire-workflow <workflow_id> <node_id> <dependency_node_id> <action> [policy]
```

Disable, enable, or remove queued nodes:

```text
/disable-workflow-node <workflow_id> <node_id>
/enable-workflow-node <workflow_id> <node_id>
/remove-workflow-node <workflow_id> <node_id>
```

### Snapshots and Export

Create a snapshot:

```bash
sol --workflow-snapshot <workflow_id> before-export
```

Export the current workflow:

```bash
sol --workflow-export <workflow_id>
```

Export a saved snapshot:

```bash
sol --workflow-export <workflow_id> <snapshot_id>
```

Interactive equivalents:

```text
/workflow-snapshot <workflow_id> [label]
/workflow-export <workflow_id> [snapshot_id]
```

## Gateway Usage

When Sol is running behind a gateway, workflow and sub-agent visibility is also available through message commands:

```text
/follow-subagent <run_id>
/follow-workflow <workflow_id>
```

That pushes progress or workflow events back into the active channel.

## Server Endpoints

Useful orchestration endpoints include:

- `GET /subagents`
- `GET /subagents/<run_id>`
- `GET /subagents/<run_id>/events`
- `GET /workflows`
- `GET /workflows/<workflow_id>`
- `GET /workflows/<workflow_id>/events`
- `POST /workflows/<workflow_id>/snapshot`
- `GET /workflows/<workflow_id>/export`

## Recommended Flow

For longer work:

1. Use Sol interactively to define the task.
2. Push repeatable or parallel work into sub-agents or workflows.
3. Watch progress with `/subagent-progress` or `/workflow-events`.
4. Snapshot and export the workflow when the DAG reaches a useful state.

## Next Planned Capability

Workflow replay and cloning are the next planned orchestration features. That roadmap item is tracked in `docs/TODO.md`.
