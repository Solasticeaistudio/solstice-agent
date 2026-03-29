# War Room Reply Playbook

## Goal

Handle most email replies without human intervention while escalating the moments that actually matter.

The agent should be able to respond gracefully to:

- requests for more information
- routing referrals
- soft objections
- timing deferrals
- light skepticism

The agent should escalate:

- demo requests
- pricing questions
- procurement, legal, or security review requests
- explicit commercial interest
- ambiguous or politically sensitive replies

Use the review queue first when needed, then prepare only safe replies:

```powershell
sol --outreach-review-replies camp-warroom-wave1 --limit 20
sol --outreach-prepare-replies camp-warroom-wave1 --limit 10 --auto-safe-only
sol --outreach-autoreply-safe camp-warroom-wave1 --limit 10
sol --outreach-autoreply-safe camp-warroom-wave1 --limit 10 --booking-link https://your-booking-link
sol --outreach-pipeline-memory camp-warroom-wave1
sol --outreach-analytics camp-warroom-wave1
sol --outreach-next-actions camp-warroom-wave1 --limit 10
sol --outreach-export-crm camp-warroom-wave1
sol --outreach-export-meetings camp-warroom-wave1
sol --outreach-push-crm camp-warroom-wave1 --crm-webhook https://your-crm-webhook
sol --outreach-push-meetings camp-warroom-wave1 --meeting-webhook https://your-meeting-webhook
```

## Safe Auto-Reply Classes

### Interested, Needs More Info

Approach:

- answer directly
- keep the response concise
- offer a one-pager or sample output
- do not over-attach collateral

### Routing Referral

Approach:

- thank them briefly
- make the message easy to forward
- continue with the referred owner

### Not Now

Approach:

- acknowledge timing
- reduce pressure
- ask permission to circle back later

### Challenge / Objection

Approach:

- answer calmly
- do not become defensive
- explain differentiation through use case and output quality
- keep the tone founder-credible, not salesy

## Escalation Classes

### Demo Request

If a booking link is configured, the agent can handle this automatically with a short scheduling reply.

If no booking link is configured, escalate because this is a positive buying signal and may require scheduling, tailoring, or live scoping.

### Pricing Request

Escalate because the agent should not improvise pricing outside the approved offer ladder.

### Procurement / Legal / Security

Escalate because these require commitments, documents, or process details that should be handled carefully.

### Ambiguous Human Review

Escalate because unclear intent is how agents create awkward threads.

## Tone Rules

- Stay calm and specific.
- Never sound desperate.
- Never overclaim traction, customers, or deployment scale.
- Answer the question that was actually asked.
- Prefer one clean next step over three options.

## Follow-Up Memory

Follow-ups should not reset context. The agent should use pipeline memory to adapt tone and content:

- `needs_info`: follow up with one concrete example or approved sample angle
- `deferred`: keep it low-pressure and respect timing
- `routed`: make it easy to forward internally
- `objection`: clarify differentiation calmly
- `demo_requested`: move toward scheduling confirmation
