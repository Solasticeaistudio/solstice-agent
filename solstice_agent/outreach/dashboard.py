"""
Dashboard
=========
Campaign reporting and pipeline visualization.
"""

import logging
from .store import get_store
from .models import CampaignStatus, LeadStage

log = logging.getLogger("solstice.outreach.dashboard")


def outreach_dashboard() -> str:
    """Full pipeline status across all campaigns."""
    store = get_store()
    campaigns = store.list_campaigns()

    if not campaigns:
        return "No outreach campaigns. Use outreach_campaign_create to start one."

    lines = ["OUTREACH DASHBOARD", "=" * 50]

    for campaign in campaigns:
        leads = store.list_leads(campaign_id=campaign.id)
        stage_counts = {}
        for lead in leads:
            stage_counts[lead.stage.value] = stage_counts.get(lead.stage.value, 0) + 1

        lines.append(f"\n{campaign.name} [{campaign.status.value.upper()}]")
        lines.append(f"  Type: {campaign.campaign_type.value}")
        lines.append(f"  Leads: {len(leads)} total")
        for stage, count in sorted(stage_counts.items()):
            lines.append(f"    {stage}: {count}")
        lines.append(f"  Emails sent: {campaign.emails_sent}")
        lines.append(f"  Replies: {campaign.replies_received}")
        reply_rate = (
            f"{campaign.replies_received / campaign.emails_sent * 100:.1f}%"
            if campaign.emails_sent > 0 else "N/A"
        )
        lines.append(f"  Reply rate: {reply_rate}")
        lines.append(f"  Meetings: {campaign.meetings_booked}")
        lines.append(f"  Opt-outs: {campaign.opted_out}")
        lines.append(f"  Bounced: {campaign.bounced}")

    metrics = store.get_today_metrics()
    lines.append(f"\nTODAY'S METRICS")
    lines.append(f"  Emails sent: {metrics.emails_sent}/500")
    lines.append(f"  Replies: {metrics.emails_received}")

    return "\n".join(lines)


def outreach_lead_detail(lead_id: str) -> str:
    """Full detail view of a lead including conversation history."""
    store = get_store()
    lead = store.get_lead(lead_id)
    if not lead:
        return f"Lead '{lead_id}' not found."

    conversation = store.get_conversation(lead_id)
    conv_lines = []
    if conversation and conversation.messages:
        for msg in conversation.messages:
            direction = "SENT" if msg.direction == "outbound" else "RECEIVED"
            conv_lines.append(f"  [{direction} {msg.timestamp[:16]}] {msg.subject}")
            conv_lines.append(f"  {msg.body[:300]}{'...' if len(msg.body) > 300 else ''}")
            conv_lines.append("")

    return (
        f"LEAD: {lead.first_name} {lead.last_name}\n"
        f"  Email: {lead.email}\n"
        f"  Title: {lead.title}\n"
        f"  Company: {lead.company} ({lead.industry})\n"
        f"  Stage: {lead.stage.value}\n"
        f"  Score: {lead.score}/100\n"
        f"  Reasons: {', '.join(lead.score_reasons)}\n"
        f"  Pain points: {', '.join(lead.pain_points)}\n"
        f"  Research: {lead.research_notes}\n"
        f"  Emails: {lead.emails_sent} sent, {lead.emails_received} received\n"
        f"  Follow-ups: {lead.follow_up_count}/{lead.max_follow_ups}\n"
        f"  Next follow-up: {lead.next_follow_up[:10] if lead.next_follow_up else 'none'}\n"
        f"\nCONVERSATION:\n" + ("\n".join(conv_lines) if conv_lines else "  No messages yet.")
    )


def outreach_follow_ups_due() -> str:
    """List leads due for follow-up emails."""
    store = get_store()
    leads = store.leads_needing_follow_up()

    if not leads:
        return "No follow-ups due."

    lines = [f"FOLLOW-UPS DUE ({len(leads)}):"]
    for lead in leads:
        lines.append(
            f"  {lead.first_name} {lead.last_name} ({lead.email})\n"
            f"    Company: {lead.company}\n"
            f"    Follow-up #{lead.follow_up_count + 1} of {lead.max_follow_ups}\n"
            f"    Last contacted: {lead.last_contacted[:10] if lead.last_contacted else 'never'}\n"
            f"    ID: {lead.id}"
        )

    return "\n".join(lines)


def outreach_send_queue() -> str:
    """List qualified leads that haven't been contacted yet."""
    store = get_store()
    qualified = store.list_leads(stage=LeadStage.QUALIFIED)

    if not qualified:
        return "No qualified leads in the send queue."

    lines = [f"SEND QUEUE ({len(qualified)} qualified leads):"]
    for lead in qualified[:20]:
        lines.append(
            f"  {lead.first_name} {lead.last_name} ({lead.email})\n"
            f"    Company: {lead.company} | Score: {lead.score}\n"
            f"    ID: {lead.id}"
        )

    return "\n".join(lines)


def outreach_prospect_auto() -> str:
    """Trigger autonomous prospecting for all active campaigns."""
    store = get_store()
    active_campaigns = store.list_campaigns(status=CampaignStatus.ACTIVE)

    if not active_campaigns:
        return "No active campaigns to prospect for."

    instructions = []
    for campaign in active_campaigns:
        current_leads = len(store.list_leads(campaign_id=campaign.id))
        if current_leads >= 100:
            continue

        instructions.append(
            f"Campaign: {campaign.name} (ID: {campaign.id})\n"
            f"  Type: {campaign.campaign_type.value}\n"
            f"  Target: {campaign.target_criteria}\n"
            f"  Search queries: {', '.join(campaign.search_queries) or 'generate based on criteria'}\n"
            f"  Current leads: {current_leads}\n\n"
            f"  Run prospect_search with relevant queries, then prospect_research, "
            f"  prospect_qualify, and prospect_add for qualified leads."
        )

    return "AUTONOMOUS PROSPECTING:\n\n" + "\n\n".join(instructions)
