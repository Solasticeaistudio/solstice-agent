# War Room Environment Reference

## Required

One LLM provider:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

## Mailbox

### SMTP

- `GATEWAY_EMAIL_ADDRESS`
- `GATEWAY_EMAIL_PASSWORD`
- `GATEWAY_EMAIL_PROVIDER=smtp`
- `GATEWAY_EMAIL_SMTP_HOST`
- `GATEWAY_EMAIL_SMTP_PORT`

### Microsoft Graph

- `GATEWAY_EMAIL_PROVIDER=graph`
- `GATEWAY_EMAIL_GRAPH_USER`

Choose one auth mode:

- direct bearer token:
  - `GATEWAY_EMAIL_GRAPH_TOKEN`
- shared Outlook/MSAL cache:
  - `GATEWAY_EMAIL_GRAPH_CREDENTIALS_PATH`
  - `GATEWAY_EMAIL_GRAPH_CACHE_PATH`
  - optional `GATEWAY_EMAIL_GRAPH_CLIENT_ID`
  - optional `GATEWAY_EMAIL_GRAPH_AUTHORITY`
  - optional `GATEWAY_EMAIL_GRAPH_SCOPES`

Default shared-cache paths already match the existing IRIS desktop integration:

- `C:\dev\Solstice-EIM\outlook_credentials.json`
- `C:\dev\Solstice-EIM\data\outlook_token.json`

## Outreach

- `SOLSTICE_OUTREACH_BOOKING_LINK`
- `SOLSTICE_OUTREACH_BOOKING_CTA`
- `SOLSTICE_OUTREACH_BOOKING_LABEL`
- `SOLSTICE_OUTREACH_CRM_WEBHOOK`
- `SOLSTICE_OUTREACH_MEETING_WEBHOOK`

## Signature Branding

- `SOLSTICE_OUTREACH_SIGNATURE_NAME`
- `SOLSTICE_OUTREACH_SIGNATURE_TITLE`
- `SOLSTICE_OUTREACH_SIGNATURE_GROUP`
- `SOLSTICE_OUTREACH_SIGNATURE_TAGLINE`
- `SOLSTICE_OUTREACH_SIGNATURE_WEBSITE`
- `SOLSTICE_OUTREACH_SIGNATURE_EMAIL`
- `SOLSTICE_OUTREACH_SIGNATURE_LOGO_URL`

## Example

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:GATEWAY_EMAIL_PROVIDER="graph"
$env:GATEWAY_EMAIL_GRAPH_USER="you@domain.com"
$env:SOLSTICE_OUTREACH_BOOKING_LINK="https://your-booking-link"
$env:SOLSTICE_OUTREACH_CRM_WEBHOOK="https://your-crm-webhook"
$env:SOLSTICE_OUTREACH_MEETING_WEBHOOK="https://your-meeting-webhook"
```

Shared-cache example:

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:GATEWAY_EMAIL_PROVIDER="graph"
$env:GATEWAY_EMAIL_ADDRESS="iris@solsticestudio.ai"
$env:GATEWAY_EMAIL_GRAPH_USER="justin@solsticestudio.ai"
$env:GATEWAY_EMAIL_GRAPH_CREDENTIALS_PATH="C:\dev\Solstice-EIM\outlook_credentials.json"
$env:GATEWAY_EMAIL_GRAPH_CACHE_PATH="C:\dev\Solstice-EIM\data\outlook_token.json"
$env:SOLSTICE_OUTREACH_SIGNATURE_NAME="Justin Meister"
$env:SOLSTICE_OUTREACH_SIGNATURE_TITLE="Founder | Solstice Studio"
$env:SOLSTICE_OUTREACH_SIGNATURE_GROUP="Solstice War Room"
$env:SOLSTICE_OUTREACH_SIGNATURE_TAGLINE="Strategic Intelligence for high-stakes decisions"
$env:SOLSTICE_OUTREACH_SIGNATURE_WEBSITE="https://solsticestudio.ai"
$env:SOLSTICE_OUTREACH_SIGNATURE_EMAIL="justin@solsticestudio.ai"
$env:SOLSTICE_OUTREACH_SIGNATURE_LOGO_URL="https://solsticestudio.ai/static/icons/favicon.ico"
```
