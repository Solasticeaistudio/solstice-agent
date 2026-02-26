"""
Outreach Tools
==============
18 tools for autonomous email outreach: campaigns, prospecting, composing, sending, tracking.
"""

import logging

from .store import get_store
from .models import Campaign, CampaignType, LeadStage
from .prospector import prospect_search, prospect_research, prospect_qualify, prospect_add
from .composer import outreach_compose, outreach_send
from .tracker import check_inbox_for_replies, get_pending_replies
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

    pitch_content = ""
    if pitch_deck_path:
        pitch_content = store.load_pitch_deck(pitch_deck_path)
        if pitch_content.startswith("Error:"):
            return pitch_content

    campaign = Campaign(
        name=name,
        campaign_type=ct,
        target_criteria=target_criteria,
        target_industries=industries,
        target_titles=titles,
        search_queries=queries,
        value_proposition=value_proposition,
        pitch_deck_path=pitch_deck_path,
        pitch_deck_content=pitch_content,
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
            f"Sent: {c.emails_sent} | Replies: {c.replies_received}"
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
        "description": "Send a composed email to a lead. Records in conversation history and schedules follow-up.",
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
        "outreach_prospect_auto": outreach_prospect_auto,
        "outreach_mark_converted": outreach_mark_converted,
    }

    for name, handler in tool_map.items():
        registry.register(name, handler, _SCHEMAS[name])

    log.info(f"Registered {len(tool_map)} outreach tools")
