# Outreach User Guide

## Purpose

This guide explains how to run the Solstice outreach operator end to end for the War Room campaign.

It covers:

- prerequisites
- campaign bootstrapping
- draft generation
- reply handling
- demo booking
- analytics
- exports and webhook handoff
- operational guardrails

## Prerequisites

You need:

- a working `solstice-agent` install
- one configured LLM provider
- mailbox credentials if you want draft or send behavior
- the War Room knowledge pack in `C:\dev\solstice-agent\docs\war_room_outreach`

Optional but recommended:

- booking link for demo handling
- webhook endpoints for CRM and meeting handoff

## Core Files

- `C:\dev\solstice-agent\docs\war_room_outreach\campaign_seed.json`
- `C:\dev\solstice-agent\docs\war_room_outreach\leads_seed.json`
- `C:\dev\solstice-agent\docs\WAR_ROOM_AGENT_BOOTSTRAP.md`
- `C:\dev\solstice-agent\docs\WAR_ROOM_FIRST_WAVE_EMAILS.md`

## Environment

### LLM

Use one of:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

### Mailbox

For SMTP:

- `GATEWAY_EMAIL_ADDRESS`
- `GATEWAY_EMAIL_PASSWORD`
- `GATEWAY_EMAIL_PROVIDER=smtp`
- `GATEWAY_EMAIL_SMTP_HOST`
- `GATEWAY_EMAIL_SMTP_PORT`

For Microsoft Graph drafts:

- `GATEWAY_EMAIL_PROVIDER=graph`
- `GATEWAY_EMAIL_GRAPH_USER`

Auth options:

- direct bearer token via `GATEWAY_EMAIL_GRAPH_TOKEN`
- shared Outlook/MSAL cache via:
  - `GATEWAY_EMAIL_GRAPH_CREDENTIALS_PATH`
  - `GATEWAY_EMAIL_GRAPH_CACHE_PATH`
  - optional `GATEWAY_EMAIL_GRAPH_CLIENT_ID`
  - optional `GATEWAY_EMAIL_GRAPH_AUTHORITY`
  - optional `GATEWAY_EMAIL_GRAPH_SCOPES`

If you are already authenticated through `C:\dev\Solstice-EIM\iris-desktop`, the default shared-cache paths already line up with:

- `C:\dev\Solstice-EIM\outlook_credentials.json`
- `C:\dev\Solstice-EIM\data\outlook_token.json`

### Outreach Automation

- `SOLSTICE_OUTREACH_BOOKING_LINK`
- `SOLSTICE_OUTREACH_BOOKING_CTA`
- `SOLSTICE_OUTREACH_BOOKING_LABEL`
- `SOLSTICE_OUTREACH_CRM_WEBHOOK`
- `SOLSTICE_OUTREACH_MEETING_WEBHOOK`

### Signature Branding

Outgoing outreach mail automatically appends a Solstice War Room signature. You can override it with:

- `SOLSTICE_OUTREACH_SIGNATURE_NAME`
- `SOLSTICE_OUTREACH_SIGNATURE_TITLE`
- `SOLSTICE_OUTREACH_SIGNATURE_GROUP`
- `SOLSTICE_OUTREACH_SIGNATURE_TAGLINE`
- `SOLSTICE_OUTREACH_SIGNATURE_WEBSITE`
- `SOLSTICE_OUTREACH_SIGNATURE_EMAIL`
- `SOLSTICE_OUTREACH_SIGNATURE_LOGO_URL`

For Graph and Outlook mailboxes, the signature is rendered as HTML and can include the logo URL.

## First Run

### 1. Load the campaign

```powershell
sol --outreach-load-seeds `
  C:\dev\solstice-agent\docs\war_room_outreach\campaign_seed.json `
  C:\dev\solstice-agent\docs\war_room_outreach\leads_seed.json
```

### 2. Prepare initial drafts

```powershell
sol --outreach-prepare-drafts camp-warroom-wave1 --limit 10 --stage qualified --email-type initial
```

### 3. Review campaign state

```powershell
sol --outreach-pipeline-memory camp-warroom-wave1
sol --outreach-analytics camp-warroom-wave1
sol --outreach-next-actions camp-warroom-wave1 --limit 10
```

## Reply Handling

### Review replies

```powershell
sol --outreach-review-replies camp-warroom-wave1 --limit 20
```

### Prepare only safe replies

```powershell
sol --outreach-prepare-replies camp-warroom-wave1 --limit 10 --auto-safe-only
```

### Let the model draft or send safe replies

```powershell
sol --outreach-autoreply-safe camp-warroom-wave1 --limit 10
```

This will:

- respond to safe informational replies
- handle routing and “not now” gracefully
- answer objections calmly
- escalate pricing, procurement, legal, and ambiguous threads

## Demo Handling

If you configure a booking link, demo-request threads can be handled automatically.

```powershell
$env:SOLSTICE_OUTREACH_BOOKING_LINK="https://your-booking-link"
sol --outreach-autoreply-safe camp-warroom-wave1 --limit 10
```

Without a booking link, demo requests remain escalated.

## Analytics And Prioritization

### Campaign analytics

```powershell
sol --outreach-analytics camp-warroom-wave1
```

### Ranked next actions

```powershell
sol --outreach-next-actions camp-warroom-wave1 --limit 10
```

This helps you decide what the agent should focus on next:

- demo-interest threads
- pricing threads
- active reply states
- routed leads
- fresh qualified leads
- defer windows that have reopened

## Exports And Downstream Handoff

### Export CRM records

```powershell
sol --outreach-export-crm camp-warroom-wave1
```

### Export meeting handoff queue

```powershell
sol --outreach-export-meetings camp-warroom-wave1
```

### Push to webhook automations

```powershell
sol --outreach-push-crm camp-warroom-wave1 --crm-webhook https://your-crm-webhook
sol --outreach-push-meetings camp-warroom-wave1 --meeting-webhook https://your-meeting-webhook
```

These are generic integration hooks intended for:

- Zapier
- Make
- n8n
- custom webhook receivers
- internal CRM adapters

## Recommended Operating Mode

### Calibration phase

- keep campaign `draft_only`
- review first-wave initial drafts
- review first-wave safe autoreplies
- confirm booking-link copy

### Semi-autonomous phase

- allow safe autoreplies
- allow booking-link demo handling
- monitor analytics and next actions daily

### Production phase

- enable downstream webhook handoff
- keep pricing, procurement, legal, and ambiguous threads escalated

## Guardrails

- Do not let the system improvise traction, customer names, pricing, or commitments.
- Keep `draft_only` enabled until mailbox and copy quality are validated.
- Use webhook pushes only after verifying the downstream receiver schema.
- Keep demo handling automated only if the booking flow is correct.

## Troubleshooting

### No emails are drafted or sent

Check mailbox configuration:

- `GATEWAY_EMAIL_ADDRESS`
- `GATEWAY_EMAIL_PASSWORD` or Graph auth
- if using shared Graph auth, verify:
  - `GATEWAY_EMAIL_GRAPH_CREDENTIALS_PATH`
  - `GATEWAY_EMAIL_GRAPH_CACHE_PATH`
  - the cached Outlook consent includes `Mail.Send`
- campaign `draft_only` mode

### Safe autoreply is not processing replies

Check:

- the lead is in `replied` or `engaged`
- the last conversation message is inbound
- the reply is classified as safe

### Demo requests are still escalated

Check:

- `SOLSTICE_OUTREACH_BOOKING_LINK` is set
- or pass `--booking-link` directly

### CRM push or meeting push fails

Check:

- webhook URL is reachable
- downstream service accepts JSON POST
- authentication is handled by the webhook layer if required

## Minimal Successful Stack

If you want the simplest setup that still works well:

1. load campaign seeds
2. keep `draft_only=true`
3. generate draft batches
4. use safe autoreply
5. configure a booking link
6. review analytics and next actions daily

That is enough to run the operator effectively without turning it into an unbounded sales bot.
