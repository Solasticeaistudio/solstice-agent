"""
Outreach Tools
==============
18 tools for autonomous email outreach: campaigns, prospecting, composing, sending, tracking.
Plus 3 Echo bridge tools: echo_send, echo_proof, echo_inbox_stats.
"""

import logging

from .echo_bridge import (
    send_via_echo as _echo_send_raw,
    preflight_proof as _echo_proof_raw,
    format_result as _echo_format,
    is_echo_available,
)
from .store import get_store
from .models import Campaign, CampaignType, LeadStage
from .seed_loader import load_seed_bundle
from .reply_triage import (
    triage_reply,
    outreach_prepare_reply_batch,
    outreach_reply_review_queue,
    outreach_pipeline_snapshot,
)
from .prospector import prospect_search, prospect_research, prospect_qualify, prospect_add
from .composer import outreach_compose, outreach_send, outreach_prepare_draft_batch
from .tracker import check_inbox_for_replies, get_pending_replies
from .analytics import outreach_analytics, outreach_next_best_actions
from .sync_queue import (
    outreach_export_crm,
    outreach_export_meeting_queue,
    outreach_push_crm,
    outreach_push_meeting_queue,
)
from .dashboard import (
    outreach_dashboard, outreach_lead_detail, outreach_follow_ups_due,
    outreach_send_queue, outreach_prospect_auto,
)
from .orchestrator import get_orchestrator

log = logging.getLogger("solstice.outreach.tools")


# ---------------------------------------------------------------------------
# Campaign management
# ---------------------------------------------------------------------------

def outreach_campaign_create(
    name: str,
    campaign_type: str = "customer",
    target_criteria: str = "",
    target_industries: str = "",
    target_titles: str = "",
    search_queries: str = "",
    value_proposition: str = "",
    pitch_deck_path: str = "",
    knowledge_dir: str = "",
    attachments_dir: str = "",
    approved_attachments: str = "",
    mailbox: str = "",
    persona_name: str = "outreach_investor",
    draft_only: bool = True,
    follow_up_days: str = "3,7,14",
    daily_send_limit: int = 50,
) -> str:
    """Create a new outreach campaign."""
    store = get_store()

    try:
        ct = CampaignType(campaign_type)
    except ValueError:
        return f"Error: campaign_type must be 'investor' or 'customer', got '{campaign_type}'"

    industries = [i.strip() for i in target_industries.split(",") if i.strip()] if target_industries else []
    titles = [t.strip() for t in target_titles.split(",") if t.strip()] if target_titles else []
    queries = [q.strip() for q in search_queries.split("|") if q.strip()] if search_queries else []
    days = [int(d.strip()) for d in follow_up_days.split(",") if d.strip()] if follow_up_days else [3, 7, 14]
    attachment_names = [a.strip() for a in approved_attachments.split(",") if a.strip()] if approved_attachments else []

    pitch_content = ""
    if pitch_deck_path:
        pitch_content = store.load_pitch_deck(pitch_deck_path)
        if pitch_content.startswith("Error:"):
            return pitch_content

    knowledge_content = ""
    if knowledge_dir:
        knowledge_content = store.load_knowledge_base(knowledge_dir)
        if knowledge_content.startswith("Error:"):
            return knowledge_content

    campaign = Campaign(
        name=name,
        campaign_type=ct,
        persona_name=persona_name,
        target_criteria=target_criteria,
        target_industries=industries,
        target_titles=titles,
        search_queries=queries,
        value_proposition=value_proposition,
        pitch_deck_path=pitch_deck_path,
        pitch_deck_content=pitch_content,
        knowledge_dir=knowledge_dir,
        knowledge_content=knowledge_content,
        attachments_dir=attachments_dir,
        approved_attachments=attachment_names,
        mailbox=mailbox,
        draft_only=draft_only,
        follow_up_days=days,
        daily_send_limit=daily_send_limit,
    )

    store.save_campaign(campaign)

    return (
        f"Campaign created: {campaign.name} (ID: {campaign.id})\n"
        f"  Type: {campaign.campaign_type.value}\n"
        f"  Target: {campaign.target_criteria}\n"
        f"  Industries: {', '.join(industries) or 'any'}\n"
        f"  Titles: {', '.join(titles) or 'any'}\n"
        f"  Search queries: {len(queries)}\n"
        f"  Pitch deck: {'loaded' if pitch_content else 'not loaded'}\n"
        f"  Knowledge base: {'loaded' if knowledge_content else 'not loaded'}\n"
        f"  Mailbox: {campaign.mailbox or 'default env mailbox'}\n"
        f"  Draft only: {campaign.draft_only}\n"
        f"  Approved attachments: {', '.join(campaign.approved_attachments) or 'none'}\n"
        f"  Follow-up schedule: day {', '.join(str(d) for d in days)}\n"
        f"  Status: DRAFT\n\n"
        f"Next: Use outreach_campaign_start to activate autonomous outreach."
    )


def outreach_campaign_start(campaign_id: str) -> str:
    """Activate a campaign to begin autonomous outreach."""
    return get_orchestrator().start_campaign(campaign_id)


def outreach_campaign_pause(campaign_id: str) -> str:
    """Pause an active campaign."""
    return get_orchestrator().pause_campaign(campaign_id)


def outreach_campaign_list() -> str:
    """List all campaigns with status."""
    store = get_store()
    campaigns = store.list_campaigns()
    if not campaigns:
        return "No campaigns. Use outreach_campaign_create to start one."

    lines = [f"Campaigns ({len(campaigns)}):"]
    for c in campaigns:
        leads = len(store.list_leads(campaign_id=c.id))
        lines.append(
            f"  {c.id} [{c.status.value.upper()}] {c.name}\n"
            f"    Type: {c.campaign_type.value} | Leads: {leads} | "
            f"Sent: {c.emails_sent} | Replies: {c.replies_received}\n"
            f"    Mailbox: {c.mailbox or 'default'} | Draft only: {c.draft_only} | "
            f"Attachments: {len(c.approved_attachments)}"
        )
    return "\n".join(lines)


def outreach_campaign_load_pitch(campaign_id: str, pitch_deck_path: str) -> str:
    """Load or update the pitch deck for a campaign."""
    store = get_store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        return f"Error: Campaign '{campaign_id}' not found."

    content = store.load_pitch_deck(pitch_deck_path)
    if content.startswith("Error:"):
        return content

    campaign.pitch_deck_path = pitch_deck_path
    campaign.pitch_deck_content = content
    store.save_campaign(campaign)

    return f"Pitch deck loaded for '{campaign.name}': {len(content)} chars from {pitch_deck_path}"


def outreach_campaign_load_knowledge(campaign_id: str, knowledge_dir: str) -> str:
    """Load or refresh the approved knowledge directory for a campaign."""
    store = get_store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        return f"Error: Campaign '{campaign_id}' not found."

    content = store.load_knowledge_base(knowledge_dir)
    if content.startswith("Error:"):
        return content

    campaign.knowledge_dir = knowledge_dir
    campaign.knowledge_content = content
    store.save_campaign(campaign)
    return f"Knowledge base loaded for '{campaign.name}': {len(content)} chars from {knowledge_dir}"


def outreach_check_inbox() -> str:
    """Check inbox for outreach replies."""
    return check_inbox_for_replies()


def outreach_pending_replies() -> str:
    """List leads with unanswered replies."""
    return get_pending_replies()


def outreach_mark_converted(lead_id: str, notes: str = "") -> str:
    """Mark a lead as converted."""
    store = get_store()
    lead = store.get_lead(lead_id)
    if not lead:
        return f"Error: Lead '{lead_id}' not found."

    lead.stage = LeadStage.CONVERTED
    if notes:
        lead.research_notes += f"\n[CONVERTED] {notes}"
    store.save_lead(lead)

    campaign = store.get_campaign(lead.campaign_id)
    if campaign:
        campaign.meetings_booked += 1
        store.save_campaign(campaign)

    return f"Lead {lead.first_name} {lead.last_name} marked as CONVERTED."


def outreach_load_seeds(
    campaign_seed_path: str,
    leads_seed_path: str,
    replace: bool = False,
    store_root: str = "",
) -> str:
    """Load campaign and lead seed JSON files into the outreach store."""
    return load_seed_bundle(
        campaign_seed_path=campaign_seed_path,
        leads_seed_path=leads_seed_path,
        store_root=store_root or None,
        replace=replace,
    )


def outreach_triage_reply(lead_id: str) -> str:
    """Classify the latest inbound reply for a lead and recommend how to handle it."""
    return triage_reply(lead_id)


def outreach_reply_review(campaign_id: str = "", limit: int = 20) -> str:
    """List pending replies with triage labels and recommended actions."""
    return outreach_reply_review_queue(campaign_id=campaign_id, limit=limit)


def outreach_pipeline_memory(campaign_id: str = "") -> str:
    """Show lead memory state including tags, latest intent, and deferrals."""
    return outreach_pipeline_snapshot(campaign_id=campaign_id)


def outreach_analytics_report(campaign_id: str = "") -> str:
    """Summarize campaign learning signals from replies, intents, and tags."""
    return outreach_analytics(campaign_id=campaign_id)


def outreach_next_actions(campaign_id: str = "", limit: int = 10) -> str:
    """Rank the next best leads or threads to act on."""
    return outreach_next_best_actions(campaign_id=campaign_id, limit=limit)


def outreach_crm_export(campaign_id: str = "") -> str:
    """Export connector-ready CRM records for a campaign or all campaigns."""
    return outreach_export_crm(campaign_id=campaign_id)


def outreach_meeting_export(campaign_id: str = "") -> str:
    """Export meeting-ready handoff records for demo or converted leads."""
    return outreach_export_meeting_queue(campaign_id=campaign_id)


def outreach_crm_push(campaign_id: str = "", webhook_url: str = "") -> str:
    """Push CRM records to a webhook endpoint."""
    return outreach_push_crm(campaign_id=campaign_id, webhook_url=webhook_url)


def outreach_meeting_push(campaign_id: str = "", webhook_url: str = "") -> str:
    """Push meeting handoff records to a webhook endpoint."""
    return outreach_push_meeting_queue(campaign_id=campaign_id, webhook_url=webhook_url)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "outreach_campaign_create": {
        "name": "outreach_campaign_create",
        "description": "Create a new outreach campaign (investor or customer). Define targeting, search queries, pitch content, and follow-up schedule.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Campaign name"},
                "campaign_type": {"type": "string", "enum": ["investor", "customer"]},
                "target_criteria": {"type": "string", "description": "Natural language targeting criteria"},
                "target_industries": {"type": "string", "description": "Comma-separated industries"},
                "target_titles": {"type": "string", "description": "Comma-separated job titles to target"},
                "search_queries": {"type": "string", "description": "Pipe-separated search queries for prospecting"},
                "value_proposition": {"type": "string", "description": "Core pitch in 2-3 sentences"},
                "pitch_deck_path": {"type": "string", "description": "Path to pitch deck file (markdown/text)"},
                "knowledge_dir": {"type": "string", "description": "Directory of approved knowledge files"},
                "attachments_dir": {"type": "string", "description": "Directory of approved outbound attachments"},
                "approved_attachments": {"type": "string", "description": "Comma-separated approved filenames"},
                "mailbox": {"type": "string", "description": "Mailbox address to draft/send from"},
                "persona_name": {"type": "string", "description": "Registered outreach personality name"},
                "draft_only": {"type": "boolean", "description": "Create drafts instead of sending"},
                "follow_up_days": {"type": "string", "description": "Comma-separated days between follow-ups (default: 3,7,14)"},
                "daily_send_limit": {"type": "integer", "description": "Max emails/day for this campaign (default: 50)"},
            },
            "required": ["name", "campaign_type"],
        },
    },
    "outreach_campaign_start": {
        "name": "outreach_campaign_start",
        "description": "Activate a campaign. Schedules autonomous prospecting, sending, inbox monitoring, and follow-ups.",
        "parameters": {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"],
        },
    },
    "outreach_campaign_pause": {
        "name": "outreach_campaign_pause",
        "description": "Pause an active campaign. Stops sending but preserves all data.",
        "parameters": {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"],
        },
    },
    "outreach_campaign_list": {
        "name": "outreach_campaign_list",
        "description": "List all outreach campaigns with status, lead count, and metrics.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "outreach_campaign_load_pitch": {
        "name": "outreach_campaign_load_pitch",
        "description": "Load or update the pitch deck for a campaign from a file.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "pitch_deck_path": {"type": "string", "description": "Path to pitch deck file"},
            },
            "required": ["campaign_id", "pitch_deck_path"],
        },
    },
    "outreach_campaign_load_knowledge": {
        "name": "outreach_campaign_load_knowledge",
        "description": "Load or refresh the approved knowledge directory for a campaign.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "knowledge_dir": {"type": "string", "description": "Directory of approved knowledge files"},
            },
            "required": ["campaign_id", "knowledge_dir"],
        },
    },
    "prospect_search": {
        "name": "prospect_search",
        "description": "Search the web for potential leads matching campaign criteria.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query for finding leads"},
                "campaign_id": {"type": "string"},
                "max_results": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["query", "campaign_id"],
        },
    },
    "prospect_research": {
        "name": "prospect_research",
        "description": "Deep research a company/person by visiting their website. Extracts contact info, details, and pain points.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "campaign_id": {"type": "string"},
            },
            "required": ["url", "campaign_id"],
        },
    },
    "prospect_qualify": {
        "name": "prospect_qualify",
        "description": "Evaluate and score a potential lead (0-100) based on campaign criteria.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "company": {"type": "string"},
                "contact_name": {"type": "string"},
                "email": {"type": "string"},
                "title": {"type": "string"},
                "industry": {"type": "string"},
                "company_description": {"type": "string"},
                "pain_points": {"type": "string", "description": "Comma-separated"},
                "research_notes": {"type": "string"},
                "source_url": {"type": "string"},
            },
            "required": ["campaign_id", "company", "contact_name", "email"],
        },
    },
    "prospect_add": {
        "name": "prospect_add",
        "description": "Add a qualified lead to a campaign.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "email": {"type": "string"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "company": {"type": "string"},
                "title": {"type": "string"},
                "industry": {"type": "string"},
                "company_url": {"type": "string"},
                "company_description": {"type": "string"},
                "pain_points": {"type": "string", "description": "Comma-separated"},
                "research_notes": {"type": "string"},
                "score": {"type": "integer", "description": "Fit score 0-100"},
                "score_reasons": {"type": "string", "description": "Comma-separated reasons"},
                "source_url": {"type": "string"},
            },
            "required": ["campaign_id", "email", "first_name", "last_name", "company"],
        },
    },
    "outreach_compose": {
        "name": "outreach_compose",
        "description": "Prepare context for composing a personalized outreach email. Returns lead profile, pitch deck, and conversation history. After reading, compose the email and call outreach_send.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "email_type": {"type": "string", "enum": ["initial", "follow_up", "reply"]},
                "custom_angle": {"type": "string", "description": "Optional personalization angle"},
            },
            "required": ["lead_id"],
        },
    },
    "outreach_send": {
        "name": "outreach_send",
        "description": "Create a draft or send a composed email to a lead, depending on campaign settings. Records in conversation history and schedules follow-up.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Composed email body"},
            },
            "required": ["lead_id", "subject", "body"],
        },
    },
    "outreach_check_inbox": {
        "name": "outreach_check_inbox",
        "description": "Check email inbox for replies to outreach. Matches to leads, detects opt-outs.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "outreach_pending_replies": {
        "name": "outreach_pending_replies",
        "description": "List leads that replied but haven't been responded to yet.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "outreach_dashboard": {
        "name": "outreach_dashboard",
        "description": "Full outreach pipeline: campaigns, lead stages, send metrics, reply rates.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "outreach_lead_detail": {
        "name": "outreach_lead_detail",
        "description": "Full details for a lead including conversation history.",
        "parameters": {
            "type": "object",
            "properties": {"lead_id": {"type": "string"}},
            "required": ["lead_id"],
        },
    },
    "outreach_follow_ups_due": {
        "name": "outreach_follow_ups_due",
        "description": "List leads due for follow-up emails.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "outreach_send_queue": {
        "name": "outreach_send_queue",
        "description": "List qualified leads that haven't been contacted yet (ready to send).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "outreach_prepare_draft_batch": {
        "name": "outreach_prepare_draft_batch",
        "description": "Prepare compose-context artifacts for a batch of leads in a campaign.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string"},
                "email_type": {"type": "string", "description": "initial, follow_up, or reply"},
                "limit": {"type": "integer", "description": "Max number of leads to prepare"},
                "stage": {"type": "string", "description": "Lead stage filter, default qualified"},
                "custom_angle": {"type": "string", "description": "Optional shared angle to include in compose context"},
            },
            "required": ["campaign_id"],
        },
    },
    "outreach_prospect_auto": {
        "name": "outreach_prospect_auto",
        "description": "Trigger autonomous prospecting for all active campaigns.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "outreach_mark_converted": {
        "name": "outreach_mark_converted",
        "description": "Mark a lead as converted (meeting booked, deal closed).",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
                "notes": {"type": "string", "description": "Conversion notes"},
            },
            "required": ["lead_id"],
        },
    },
    "outreach_load_seeds": {
        "name": "outreach_load_seeds",
        "description": "Load a campaign seed JSON object and lead seed JSON array into the outreach store.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_seed_path": {"type": "string", "description": "Path to campaign seed JSON"},
                "leads_seed_path": {"type": "string", "description": "Path to leads seed JSON"},
                "replace": {"type": "boolean", "description": "Overwrite existing campaign and matching leads"},
                "store_root": {"type": "string", "description": "Optional outreach store root override"},
            },
            "required": ["campaign_seed_path", "leads_seed_path"],
        },
    },
    "outreach_triage_reply": {
        "name": "outreach_triage_reply",
        "description": "Classify the latest inbound reply for a lead and recommend whether to auto-reply or escalate.",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string"},
            },
            "required": ["lead_id"],
        },
    },
    "outreach_prepare_reply_batch": {
        "name": "outreach_prepare_reply_batch",
        "description": "Prepare reply compose artifacts for pending inbound replies and escalate sensitive ones.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
                "limit": {"type": "integer", "description": "Max pending replies to process"},
                "auto_safe_only": {"type": "boolean", "description": "Prepare only replies deemed safe for autonomy"},
            },
            "required": [],
        },
    },
    "outreach_reply_review": {
        "name": "outreach_reply_review",
        "description": "Review pending replies with triage labels, safety status, and recommended actions.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
                "limit": {"type": "integer", "description": "Max pending replies to display"},
            },
            "required": [],
        },
    },
    "outreach_pipeline_memory": {
        "name": "outreach_pipeline_memory",
        "description": "Show lead memory state including tags, latest detected intent, and deferred follow-up dates.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
            },
            "required": [],
        },
    },
    "outreach_analytics_report": {
        "name": "outreach_analytics_report",
        "description": "Summarize campaign learning signals from replies, intents, and tagged pipeline memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
            },
            "required": [],
        },
    },
    "outreach_next_actions": {
        "name": "outreach_next_actions",
        "description": "Rank the next best leads or reply threads to act on.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
                "limit": {"type": "integer", "description": "Max ranked leads to show"},
            },
            "required": [],
        },
    },
    "outreach_crm_export": {
        "name": "outreach_crm_export",
        "description": "Export connector-ready CRM records for a campaign or all campaigns.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
            },
            "required": [],
        },
    },
    "outreach_meeting_export": {
        "name": "outreach_meeting_export",
        "description": "Export meeting handoff records for demo or converted leads.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
            },
            "required": [],
        },
    },
    "outreach_crm_push": {
        "name": "outreach_crm_push",
        "description": "Push CRM records to a webhook endpoint.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
                "webhook_url": {"type": "string", "description": "Webhook target URL"},
            },
            "required": ["webhook_url"],
        },
    },
    "outreach_meeting_push": {
        "name": "outreach_meeting_push",
        "description": "Push meeting handoff records to a webhook endpoint.",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Optional campaign filter"},
                "webhook_url": {"type": "string", "description": "Webhook target URL"},
            },
            "required": ["webhook_url"],
        },
    },
}


# ---------------------------------------------------------------------------
# Echo bridge tool functions
# ---------------------------------------------------------------------------

def echo_send(
    to: str,
    subject: str,
    body: str,
    from_addr: str = "outreach@solsticestudio.ai",
    trigger: str = "",
    trigger_recency_days: float = 999,
    relationship_hints: str = "",
    value_offer: str = "",
    recipient_tz: str = "+00:00",
    urgent: bool = False,
) -> str:
    """Send an email through Echo's 8-dimension authenticity pipeline. Returns status string."""
    import json
    hints = {}
    if relationship_hints:
        try:
            hints = json.loads(relationship_hints)
        except Exception:
            hints = {"note": relationship_hints}

    try:
        result = _echo_send_raw(
            to=to, from_addr=from_addr, subject=subject, body_text=body,
            trigger_event=trigger, trigger_recency_days=trigger_recency_days,
            relationship_hints=hints, value_offer=value_offer,
            recipient_tz=recipient_tz, urgent=urgent, sync=True,
        )
        return _echo_format(result)
    except Exception as e:
        return f"Echo error: {e}"


def echo_proof(
    to: str,
    subject: str,
    body: str,
    from_addr: str = "outreach@solsticestudio.ai",
    trigger: str = "",
) -> str:
    """Pre-flight authenticity score a message without sending. Returns PASS/BLOCK + score breakdown."""
    import requests as _req
    import os
    ECHO_URL = os.getenv("ECHO_DELIVERY_URL", "http://localhost:5000")
    try:
        r = _req.post(
            f"{ECHO_URL}/api/echo/delivery/proof",
            json={
                "recipient_address": to, "sender_address": from_addr,
                "channel": "email", "subject": subject, "body_text": body,
                "trigger_event": trigger,
            },
            timeout=10,
        )
        d = r.json()
        score = d.get("calibrated_composite", 0)
        passed = d.get("passed")
        verdict = "PASS" if passed else ("HARD BLOCK" if d.get("hard_blocked") else "BLOCK")
        dims = " | ".join(
            f"{x['name'].replace('_',' ')}={x['raw']:.0%}"
            for x in (d.get("dimensions") or [])[:5]
        )
        reason = d.get("block_reason", "")
        return f"{verdict} score={score:.2f}/1.00  threshold={d.get('threshold',0.62)}\n{dims}" + (f"\nReason: {reason}" if reason else "")
    except Exception as e:
        return f"Echo unavailable: {e}"


def echo_inbox_stats(hours: int = 24) -> str:
    """Get Echo inbox bucket stats for the last N hours."""
    import requests as _req
    import os
    ECHO_URL = os.getenv("ECHO_DELIVERY_URL", "http://localhost:5000")
    try:
        r = _req.get(f"{ECHO_URL}/api/echo/delivery/inbox/stats?hours={hours}", timeout=5)
        d = r.json()
        return (
            f"Inbox last {hours}h: {d.get('total',0)} messages — "
            f"Priority {d.get('priority',0)}, Review {d.get('review',0)}, "
            f"Low {d.get('low',0)}, Blocked {d.get('blocked',0)}. "
            f"Rule hits: {d.get('rule_matches',0)}. Avg score: {d.get('avg_score',0):.2f}"
        )
    except Exception as e:
        return f"Echo unavailable: {e}"


_ECHO_SCHEMAS = {
    "echo_send": {
        "name": "echo_send",
        "description": (
            "Send an email through Echo's authenticity-first delivery pipeline. "
            "The message is scored across 8 dimensions before sending. "
            "Hard blocks if relationship_depth=0 and trigger_relevance<0.3. "
            "Use echo_proof first to check the score before committing to a send."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to":                   {"type": "string",  "description": "Recipient email address"},
                "subject":              {"type": "string",  "description": "Email subject line"},
                "body":                 {"type": "string",  "description": "Plain-text email body"},
                "from_addr":            {"type": "string",  "description": "Sender email address"},
                "trigger":              {"type": "string",  "description": "The 'why now' event: job_change, funding_round, product_launch, conference_met, etc."},
                "trigger_recency_days": {"type": "number",  "description": "Days since the trigger event (lower = more timely)"},
                "relationship_hints":   {"type": "string",  "description": "JSON string with context: {met_at, mutual, prior_convo}"},
                "value_offer":          {"type": "string",  "description": "Specific concrete value offer in ≤200 chars"},
                "recipient_tz":         {"type": "string",  "description": "UTC offset e.g. -05:00"},
                "urgent":               {"type": "boolean", "description": "Skip time-window constraint"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    "echo_proof": {
        "name": "echo_proof",
        "description": (
            "Pre-flight check: score a message's authenticity without sending. "
            "Returns PASS/BLOCK verdict and per-dimension scores. "
            "Always run this before echo_send for important sends."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to":        {"type": "string", "description": "Recipient email"},
                "subject":   {"type": "string", "description": "Subject line"},
                "body":      {"type": "string", "description": "Plain-text body"},
                "from_addr": {"type": "string", "description": "Sender email"},
                "trigger":   {"type": "string", "description": "Why now? event context"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    "echo_inbox_stats": {
        "name": "echo_inbox_stats",
        "description": "Get Echo inbound inbox bucket stats: how many emails were Priority, Review, Low, Blocked in the last N hours.",
        "parameters": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Look-back window in hours (default 24)"},
            },
            "required": [],
        },
    },
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_outreach_tools(registry):
    """Register all outreach tools with a ToolRegistry."""
    tool_map = {
        "outreach_campaign_create": outreach_campaign_create,
        "outreach_campaign_start": outreach_campaign_start,
        "outreach_campaign_pause": outreach_campaign_pause,
        "outreach_campaign_list": outreach_campaign_list,
        "outreach_campaign_load_pitch": outreach_campaign_load_pitch,
        "outreach_campaign_load_knowledge": outreach_campaign_load_knowledge,
        "prospect_search": prospect_search,
        "prospect_research": prospect_research,
        "prospect_qualify": prospect_qualify,
        "prospect_add": prospect_add,
        "outreach_compose": outreach_compose,
        "outreach_send": outreach_send,
        "outreach_check_inbox": outreach_check_inbox,
        "outreach_pending_replies": outreach_pending_replies,
        "outreach_dashboard": outreach_dashboard,
        "outreach_lead_detail": outreach_lead_detail,
        "outreach_follow_ups_due": outreach_follow_ups_due,
        "outreach_send_queue": outreach_send_queue,
        "outreach_prepare_draft_batch": outreach_prepare_draft_batch,
        "outreach_prospect_auto": outreach_prospect_auto,
        "outreach_mark_converted": outreach_mark_converted,
        "outreach_load_seeds": outreach_load_seeds,
        "outreach_triage_reply": outreach_triage_reply,
        "outreach_reply_review": outreach_reply_review,
        "outreach_pipeline_memory": outreach_pipeline_memory,
        "outreach_analytics_report": outreach_analytics_report,
        "outreach_next_actions": outreach_next_actions,
        "outreach_crm_export": outreach_crm_export,
        "outreach_meeting_export": outreach_meeting_export,
        "outreach_crm_push": outreach_crm_push,
        "outreach_meeting_push": outreach_meeting_push,
        "outreach_prepare_reply_batch": outreach_prepare_reply_batch,
        # Echo delivery bridge
        "echo_send":         echo_send,
        "echo_proof":        echo_proof,
        "echo_inbox_stats":  echo_inbox_stats,
    }

    combined_schemas = {**_SCHEMAS, **_ECHO_SCHEMAS}

    for name, handler in tool_map.items():
        registry.register(name, handler, combined_schemas[name])

    if is_echo_available():
        log.info("Echo delivery pipeline: CONNECTED at %s", __import__('os').getenv('ECHO_DELIVERY_URL', 'http://localhost:5000'))
    else:
        log.warning("Echo delivery pipeline: OFFLINE — echo_send/echo_proof will error until main.py is running")

    log.info(f"Registered {len(tool_map)} outreach tools ({len(_ECHO_SCHEMAS)} Echo bridge)")
