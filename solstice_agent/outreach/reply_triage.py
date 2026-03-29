"""
Reply Triage
============
Heuristic reply classification and safe auto-reply preparation.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .composer import outreach_compose
from .models import LeadStage
from .store import get_store


_INTENT_PATTERNS: List[Tuple[str, List[str]]] = [
    ("unsubscribe", [r"\bunsubscribe\b", r"\bremove me\b", r"\bstop emailing\b", r"\bdon'?t contact\b"]),
    ("demo_request", [r"\bdemo\b", r"\bwalkthrough\b", r"\bshow me\b", r"\bsee this\b", r"\bbook (a )?call\b", r"\btalk next week\b"]),
    ("pricing_request", [r"\bprice\b", r"\bpricing\b", r"\bcost\b", r"\bbudget\b", r"\bcommercials?\b", r"\bhow much\b"]),
    ("procurement_only", [r"\bprocurement\b", r"\bvendor form\b", r"\bsecurity review\b", r"\bMSA\b", r"\bNDA\b", r"\blegal\b"]),
    ("routing_referral", [r"\breach out to\b", r"\bcontact\b.+\binstead\b", r"\bloop in\b", r"\bforward\b", r"\bright person\b", r"\btry\b.+\bteam\b"]),
    ("not_now", [r"\bnot now\b", r"\bnot at this time\b", r"\bcircle back\b", r"\breach out later\b", r"\bthis quarter\b", r"\bnext quarter\b"]),
    ("not_a_fit", [r"\bnot a fit\b", r"\bno interest\b", r"\bnot relevant\b", r"\bno need\b", r"\bpass\b"]),
    ("interested_needs_more_info", [r"\bsend\b.+\bsample\b", r"\bmore info\b", r"\bmore detail\b", r"\bone-pager\b", r"\bexamples?\b"]),
    ("interested", [r"\binterested\b", r"\bworth discussing\b", r"\bopen to\b", r"\blet'?s talk\b", r"\bcurious\b"]),
]

_OBJECTION_PATTERNS = [
    r"\bhow is this different\b",
    r"\bwhy wouldn'?t\b",
    r"\bconcern\b",
    r"\bskeptical\b",
    r"\bconvince me\b",
    r"\bwhat makes\b",
]


def triage_reply(lead_id: str) -> str:
    store = get_store()
    lead = store.get_lead(lead_id)
    if not lead:
        return f"Error: Lead '{lead_id}' not found."

    conversation = store.get_conversation(lead_id)
    if not conversation or not conversation.messages:
        return f"Error: No conversation history for lead '{lead_id}'."

    last_inbound = _latest_inbound(conversation.messages)
    if not last_inbound:
        return f"No inbound reply found for lead '{lead_id}'."

    result = _classify_reply(last_inbound.body)
    _apply_pipeline_memory(lead, result)
    store.save_lead(lead)
    lines = [
        f"Reply triage for {lead.first_name} {lead.last_name} ({lead.company})",
        f"  Intent: {result['intent']}",
        f"  Safe to auto-reply: {'yes' if result['safe_to_auto_reply'] else 'no'}",
        f"  Recommended action: {result['recommended_action']}",
    ]
    if result["reason"]:
        lines.append(f"  Reason: {result['reason']}")
    if result["custom_angle"]:
        lines.append(f"  Custom angle: {result['custom_angle']}")
    return "\n".join(lines)


def outreach_prepare_reply_batch(
    campaign_id: str = "",
    limit: int = 10,
    auto_safe_only: bool = True,
) -> str:
    """
    Prepare reply compose artifacts for pending inbound replies.
    Safe intents get auto-prepared; sensitive intents are surfaced for human review.
    """
    store = get_store()
    pending = _pending_reply_leads(campaign_id=campaign_id)

    if not pending:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No pending replies found for {scope}."

    prepared = []
    escalations = []

    for lead, body in pending[:max(limit, 0)]:
        triage = _classify_reply(body)
        _apply_pipeline_memory(lead, triage)
        store.save_lead(lead)
        if auto_safe_only and not triage["safe_to_auto_reply"]:
            escalations.append((lead, triage))
            continue

        if not auto_safe_only and triage["intent"] in {"unsubscribe", "not_a_fit"}:
            escalations.append((lead, triage))
            continue

        context = outreach_compose(
            lead.id,
            email_type="reply",
            custom_angle=triage["custom_angle"],
        )
        artifact = store.save_compose_artifact(
            lead_id=lead.id,
            email_type="reply",
            context=context,
            metadata={
                "campaign_id": lead.campaign_id,
                "lead_email": lead.email,
                "company": lead.company,
                "triage_intent": triage["intent"],
                "recommended_action": triage["recommended_action"],
                "safe_to_auto_reply": triage["safe_to_auto_reply"],
            },
        )
        prepared.append((lead, triage, artifact))

    lines = [
        f"Prepared reply artifacts: {len(prepared)}",
        f"Escalations: {len(escalations)}",
    ]
    for lead, triage, artifact in prepared:
        lines.append(
            f"  PREPARED {lead.first_name} {lead.last_name} ({lead.company})\n"
            f"    Intent: {triage['intent']}\n"
            f"    Artifact: {artifact}"
        )
    for lead, triage in escalations:
        lines.append(
            f"  ESCALATE {lead.first_name} {lead.last_name} ({lead.company})\n"
            f"    Intent: {triage['intent']}\n"
            f"    Action: {triage['recommended_action']}"
        )
    return "\n".join(lines)


def outreach_reply_review_queue(campaign_id: str = "", limit: int = 20) -> str:
    """List pending replies with triage labels so the agent or operator can process them in priority order."""
    pending = _pending_reply_leads(campaign_id=campaign_id)
    if not pending:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No pending replies found for {scope}."

    lines = [f"PENDING REPLY REVIEW ({min(len(pending), max(limit, 0))} shown):"]
    for lead, body in pending[:max(limit, 0)]:
        triage = _classify_reply(body)
        _apply_pipeline_memory(lead, triage)
        get_store().save_lead(lead)
        lines.append(
            f"  {lead.first_name} {lead.last_name} ({lead.email}) [{lead.company}]\n"
            f"    Lead ID: {lead.id}\n"
            f"    Intent: {triage['intent']}\n"
            f"    Safe: {'yes' if triage['safe_to_auto_reply'] else 'no'}\n"
            f"    Action: {triage['recommended_action']}\n"
            f"    Tags: {', '.join(lead.tags) or 'none'}\n"
            f"    Deferred until: {lead.deferred_until[:10] if lead.deferred_until else 'none'}\n"
            f"    Last reply: {body[:180]}{'...' if len(body) > 180 else ''}"
        )
    return "\n".join(lines)


def outreach_pipeline_snapshot(campaign_id: str = "") -> str:
    """Show pipeline-memory-centric view of leads with tags, intents, and deferrals."""
    store = get_store()
    leads = store.list_leads(campaign_id=campaign_id or None)
    if not leads:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No leads found for {scope}."

    tagged = [lead for lead in leads if lead.tags or lead.last_detected_intent or lead.deferred_until]
    if not tagged:
        return "No leads have pipeline memory yet."

    lines = [f"PIPELINE MEMORY ({len(tagged)} leads):"]
    for lead in tagged:
        lines.append(
            f"  {lead.first_name} {lead.last_name} ({lead.company})\n"
            f"    Stage: {lead.stage.value}\n"
            f"    Intent: {lead.last_detected_intent or 'unknown'}\n"
            f"    Tags: {', '.join(lead.tags) or 'none'}\n"
            f"    Deferred until: {lead.deferred_until[:10] if lead.deferred_until else 'none'}\n"
            f"    Last pipeline update: {lead.last_pipeline_update[:16] if lead.last_pipeline_update else 'never'}"
        )
    return "\n".join(lines)


def _pending_reply_leads(campaign_id: str = ""):
    store = get_store()
    leads = []
    for stage in (LeadStage.REPLIED, LeadStage.ENGAGED):
        leads.extend(store.list_leads(campaign_id=campaign_id or None, stage=stage))

    pending = []
    for lead in leads:
        conversation = store.get_conversation(lead.id)
        if not conversation or not conversation.messages:
            continue
        last_msg = conversation.messages[-1]
        if last_msg.direction != "inbound":
            continue
        pending.append((lead, last_msg.body))
    return pending


def _latest_inbound(messages):
    for msg in reversed(messages):
        if msg.direction == "inbound":
            return msg
    return None


def _classify_reply(body: str) -> Dict[str, object]:
    text = (body or "").strip()
    lower = text.lower()

    for intent, patterns in _INTENT_PATTERNS:
        if any(re.search(p, lower) for p in patterns):
            return _intent_payload(intent, lower)

    if any(re.search(p, lower) for p in _OBJECTION_PATTERNS):
        return _intent_payload("challenge_objection", lower)

    if "?" in text:
        return _intent_payload("ambiguous_human_review", lower)

    return _intent_payload("ambiguous_human_review", lower)


def _intent_payload(intent: str, lower: str) -> Dict[str, object]:
    mapping = {
        "unsubscribe": {
            "safe": False,
            "action": "Do not reply. Respect opt-out and stop contact.",
            "reason": "Explicit opt-out language detected.",
            "angle": "No reply should be sent. Respect the opt-out immediately.",
        },
        "demo_request": {
            "safe": False,
            "action": "Escalate for human handling or scheduling. This is a positive meeting signal.",
            "reason": "Lead appears ready for a demo or live call.",
            "angle": "Acknowledge interest, offer to coordinate a short demo, and avoid improvising availability or logistics.",
        },
        "pricing_request": {
            "safe": False,
            "action": "Escalate for human pricing response.",
            "reason": "Commercial scope or pricing language detected.",
            "angle": "Respond clearly, keep trust, and avoid inventing pricing details outside the approved offer ladder.",
        },
        "procurement_only": {
            "safe": False,
            "action": "Escalate for procurement, legal, or security review handling.",
            "reason": "Procurement or legal workflow language detected.",
            "angle": "Acknowledge process requirements and avoid making legal or security commitments without review.",
        },
        "routing_referral": {
            "safe": True,
            "action": "Reply briefly, thank them, and continue with the referred owner.",
            "reason": "Internal routing or referral signal detected.",
            "angle": "Thank them for the routing help, keep the reply short, and make it easy to forward internally.",
        },
        "not_now": {
            "safe": True,
            "action": "Reply gracefully, reduce pressure, and ask for permission to circle back later.",
            "reason": "Delay or defer language detected.",
            "angle": "Acknowledge timing, keep the door open, and propose reconnecting later without pressure.",
        },
        "not_a_fit": {
            "safe": False,
            "action": "Do not press. Optionally send a very brief courtesy close if appropriate.",
            "reason": "Explicit rejection or poor fit language detected.",
            "angle": "Keep it graceful and final. Do not try to rescue the conversation.",
        },
        "interested_needs_more_info": {
            "safe": True,
            "action": "Reply with concise detail and offer a sample output or one-pager.",
            "reason": "Lead requested more detail, examples, or materials.",
            "angle": "Answer directly, send only approved materials, and keep the next step low-friction.",
        },
        "interested": {
            "safe": True,
            "action": "Reply positively, tighten relevance, and move toward a concrete next step.",
            "reason": "General positive interest language detected.",
            "angle": "Reinforce fit, keep momentum, and propose a simple next step without over-selling.",
        },
        "challenge_objection": {
            "safe": True,
            "action": "Reply calmly, answer the concern directly, and avoid defensiveness.",
            "reason": "Objection or skepticism language detected.",
            "angle": "Answer the challenge with clarity and restraint. Explain differentiation or scope without sounding combative.",
        },
        "ambiguous_human_review": {
            "safe": False,
            "action": "Escalate for human review.",
            "reason": "Reply contains unclear or mixed intent.",
            "angle": "Do not guess. Clarify the reply only after review.",
        },
    }
    payload = mapping[intent]
    return {
        "intent": intent,
        "safe_to_auto_reply": payload["safe"],
        "recommended_action": payload["action"],
        "reason": payload["reason"],
        "custom_angle": payload["angle"],
    }


def _apply_pipeline_memory(lead, triage: Dict[str, object]):
    now = datetime.now(timezone.utc).isoformat()
    intent = str(triage.get("intent") or "")
    lead.last_detected_intent = intent
    lead.last_pipeline_update = now

    _add_tag(lead, f"intent:{intent}")

    if intent == "demo_request":
        _add_tag(lead, "demo_requested")
    elif intent == "pricing_request":
        _add_tag(lead, "pricing_requested")
    elif intent == "procurement_only":
        _add_tag(lead, "procurement")
    elif intent == "routing_referral":
        _add_tag(lead, "routed")
    elif intent == "interested_needs_more_info":
        _add_tag(lead, "needs_info")
    elif intent == "challenge_objection":
        _add_tag(lead, "objection")
    elif intent == "not_now":
        _add_tag(lead, "deferred")
        lead.deferred_until = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
        lead.next_follow_up = lead.deferred_until
    elif intent == "not_a_fit":
        _add_tag(lead, "closed_lost")
    elif intent == "unsubscribe":
        _add_tag(lead, "opt_out")
    elif intent == "interested":
        _add_tag(lead, "engaged_positive")

    note = f"{now[:10]} intent={intent}"
    if not lead.pipeline_notes or lead.pipeline_notes[-1] != note:
        lead.pipeline_notes.append(note)
        if len(lead.pipeline_notes) > 10:
            lead.pipeline_notes = lead.pipeline_notes[-10:]


def _add_tag(lead, tag: str):
    if tag not in lead.tags:
        lead.tags.append(tag)
