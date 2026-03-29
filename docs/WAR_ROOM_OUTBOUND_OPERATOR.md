# War Room Outbound Operator Spec

## Purpose

This document defines how `solstice-agent` should operate as a controlled outbound operator for War Room.

The agent is not a fully autonomous salesperson. It is an outreach operator that:

- keeps campaign state clean
- personalizes messaging
- respects approved knowledge
- routes replies correctly
- escalates important conversations to Justin

## Agent Responsibilities

The outbound operator should:

1. load or maintain the War Room campaign
2. classify leads by segment and persona
3. draft personalized initial emails
4. monitor inbox replies
5. classify reply intent
6. draft follow-ups or responses
7. maintain lead state and campaign metrics
8. escalate high-value or ambiguous conversations for human review

## Operating Model

### Inputs

- approved War Room knowledge directory
- approved attachments directory
- campaign targeting criteria
- list of prioritized leads
- mailbox configuration

### Outputs

- outbound drafts or sent emails
- reply classifications
- next action recommendations
- campaign metrics
- preserved conversation history

## Reply Intent Classes

Use the following intent buckets:

- interested
- interested_needs_more_info
- routing_referral
- not_now
- not_a_fit
- unsubscribe
- procurement_only
- ambiguous_human_review

## Escalation Rules

Escalate to Justin when:

- a lead asks pricing questions beyond the approved offer ladder
- a lead requests sensitive claims, references, or unsupported proof
- a lead wants a live scoping call
- a lead appears high-value and engaged
- a reply is ambiguous or politically sensitive
- a defense or national security conversation turns substantive

Do not autonomously improvise on:

- revenue claims
- customer references
- proprietary data access
- deployment scale
- legal or security guarantees

## Drafting Rules

- Draft from approved knowledge only.
- Use concrete company-specific context when available.
- Stay concise and easy to forward.
- Always give a low-friction next step.
- For routing contacts, optimize for internal handoff.
- For named operators, optimize for a pilot conversation.
- Never send more than the campaign send limit.
- Immediately stop outreach on unsubscribe or explicit rejection.

## Lead Stage Guidance

- DISCOVERED: lead exists but is not researched enough
- QUALIFIED: enough fit to contact
- CONTACTED: initial outbound sent
- REPLIED: inbound received and waiting on classification
- ENGAGED: active two-way conversation
- CONVERTED: pilot call, meeting, or active evaluation started
- LOST: not a fit or explicit decline
- BOUNCED: invalid destination

## Initial MVP Workflow

1. Create the campaign in draft mode.
2. Load the War Room knowledge directory.
3. Add the Tier 1 first-wave targets as leads.
4. Draft initial emails only.
5. Review and approve the strongest drafts.
6. Send in small daily batches.
7. Monitor replies and classify intent.
8. Draft follow-ups automatically, but escalate strong replies.

## Recommended Campaign Defaults

- draft_only: true during first calibration wave
- daily_send_limit: 10
- follow_up_days: 3,7,14
- campaign_type: customer
- persona_name: outreach_customer

## Suggested Tool Flow

Typical agent loop:

1. `outreach_campaign_create`
2. `outreach_campaign_load_knowledge`
3. `prospect_add`
4. `outreach_compose`
5. `outreach_send`
6. `outreach_check_inbox`
7. `outreach_pending_replies`
8. `outreach_compose` with `email_type=reply`
9. `outreach_send`
10. `outreach_dashboard`

## Human Review Threshold

If a conversation has any of the following, pause automation and escalate:

- legal review
- pricing negotiation
- procurement process
- request for references or case studies
- request for technical architecture details
- live decision or live deal discussion
