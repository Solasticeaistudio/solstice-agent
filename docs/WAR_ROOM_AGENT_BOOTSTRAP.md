# War Room Agent Bootstrap

## Goal

Stand up a draft-first outbound campaign in `solstice-agent` for War Room using the existing outreach tools and the approved knowledge pack in `docs/war_room_outreach`.

## Approved Knowledge Directory

Use:

`C:\dev\solstice-agent\docs\war_room_outreach`

## Recommended Campaign Settings

- name: `War Room Wave 1`
- campaign_type: `customer`
- persona_name: `outreach_war_room`
- draft_only: `true`
- follow_up_days: `3,7,14`
- daily_send_limit: `10`

Suggested value proposition:

`Paid Decision Sprint that stress-tests a high-stakes decision and returns a board-ready brief with vulnerabilities, counterfactuals, and evidence-linked rationale in hours.`

Suggested targeting:

- target_criteria: `Strategy, portfolio, risk, and decision owners facing high-uncertainty decisions`
- target_industries: `Private Equity, Insurance, Reinsurance, Risk Analytics, Defense, National Security`
- target_titles: `Operating Partner, Portfolio Ops, Value Creation, Corporate Development, Strategy, Innovation, Risk Strategy`

## Suggested Campaign Create Call

Use a create call shaped like this:

```text
outreach_campaign_create(
  name="War Room Wave 1",
  campaign_type="customer",
  target_criteria="Strategy, portfolio, risk, and decision owners facing high-uncertainty decisions",
  target_industries="Private Equity, Insurance, Reinsurance, Risk Analytics, Defense, National Security",
  target_titles="Operating Partner, Portfolio Ops, Value Creation, Corporate Development, Strategy, Innovation, Risk Strategy",
  value_proposition="Paid Decision Sprint that stress-tests a high-stakes decision and returns a board-ready brief with vulnerabilities, counterfactuals, and evidence-linked rationale in hours.",
  knowledge_dir="C:\\dev\\solstice-agent\\docs\\war_room_outreach",
  persona_name="outreach_war_room",
  draft_only=True,
  follow_up_days="3,7,14",
  daily_send_limit=10
)
```

## Suggested Initial Lead Set

Start with:

- Greg Barber, Kingswood Capital
- Jim Renna, Kingswood Capital
- Carlin Capital Partners
- Verisk
- Moody's
- S&P Global
- Gartner
- Swiss Re
- Munich Re
- Keith McCue, RenaissanceRe
- Aon
- Marsh McLennan

Machine-readable seeds are available at:

- `C:\\dev\\solstice-agent\\docs\\war_room_outreach\\campaign_seed.json`
- `C:\\dev\\solstice-agent\\docs\\war_room_outreach\\leads_seed.json`

## Seed Loader

The outreach package now exposes a direct seed importer:

```python
from solstice_agent.outreach import load_seed_bundle

print(
    load_seed_bundle(
        r"C:\dev\solstice-agent\docs\war_room_outreach\campaign_seed.json",
        r"C:\dev\solstice-agent\docs\war_room_outreach\leads_seed.json",
    )
)
```

Use `replace=True` if you want to overwrite the existing seeded campaign and update matching leads by email.

CLI equivalent:

```powershell
sol --outreach-load-seeds `
  C:\dev\solstice-agent\docs\war_room_outreach\campaign_seed.json `
  C:\dev\solstice-agent\docs\war_room_outreach\leads_seed.json
```

## Prepare First-Wave Draft Queue

Once the campaign is loaded, prepare the first compose batch:

```powershell
sol --outreach-prepare-drafts camp-warroom-wave1 --limit 10 --stage qualified --email-type initial
```

This creates compose-context artifacts in the outreach drafts store for each eligible lead, which gives you a clean draft queue for the first wave without hand-running `outreach_compose` lead by lead.

Follow-up drafts are state-aware. If a lead was deferred, asked for more info, routed you internally, or raised an objection, that memory is injected into the compose context automatically.

## Prepare Pending Replies

When replies come in, prepare safe reply drafts and surface sensitive ones:

```powershell
sol --outreach-prepare-replies camp-warroom-wave1 --limit 10 --auto-safe-only
```

Safe classes are auto-prepared for reply drafting. Demo requests, pricing, procurement, legal, and ambiguous replies are escalated instead of being answered blindly.

To inspect the reply queue before drafting:

```powershell
sol --outreach-review-replies camp-warroom-wave1 --limit 20
```

To inspect accumulated pipeline memory and tagged lead state:

```powershell
sol --outreach-pipeline-memory camp-warroom-wave1
```

To inspect campaign learning and prioritization:

```powershell
sol --outreach-analytics camp-warroom-wave1
sol --outreach-next-actions camp-warroom-wave1 --limit 10
```

To export connector-ready CRM and meeting handoff records:

```powershell
sol --outreach-export-crm camp-warroom-wave1
sol --outreach-export-meetings camp-warroom-wave1
```

To push them directly into downstream automations via webhook:

```powershell
sol --outreach-push-crm camp-warroom-wave1 --crm-webhook https://your-crm-webhook
sol --outreach-push-meetings camp-warroom-wave1 --meeting-webhook https://your-meeting-webhook
```

To let the configured model draft or send safe replies automatically:

```powershell
sol --outreach-autoreply-safe camp-warroom-wave1 --limit 10
```

This only touches replies triaged as safe. Demo requests, pricing, procurement, legal, and ambiguous threads are left for review.

If you want demo requests handled automatically too, configure a booking link:

```powershell
$env:SOLSTICE_OUTREACH_BOOKING_LINK="https://your-booking-link"
sol --outreach-autoreply-safe camp-warroom-wave1 --limit 10
```

Or pass it directly:

```powershell
sol --outreach-autoreply-safe camp-warroom-wave1 --limit 10 --booking-link https://your-booking-link
```

## Operating Guidance

### Phase 1

- add the twelve first-wave leads
- generate initial drafts only
- review for tone and segment fit
- send in small batches

### Phase 2

- watch routing behavior
- classify replies
- escalate strong interest
- update target ranking based on real response quality

### Phase 3

- expand into Tier 2 defense and reinsurance accounts
- only after the language is validated

## Automation Guardrails

- keep the campaign in draft mode until the first batch is reviewed
- do not let the agent improvise metrics or logos
- route pricing or scoping questions to Justin
- stop immediately on unsubscribe or explicit no

## Recommended Success Metrics

- routing rate
- positive reply rate
- sample-output request rate
- meeting-booked rate
- by-segment reply quality
