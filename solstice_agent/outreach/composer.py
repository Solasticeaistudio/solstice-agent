"""
Email Composer
==============
Assembles personalization context for Sol to compose outreach emails.
Handles draft creation or sending plus conversation recording.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from .store import get_store
from .models import LeadStage, EmailMessage, Conversation

log = logging.getLogger("solstice.outreach.composer")


def outreach_compose(lead_id: str, email_type: str = "initial", custom_angle: str = "") -> str:
    """
    Prepare context for Sol to compose a personalized outreach email.
    Sol reads this context, writes the email, then calls outreach_send.
    """
    store = get_store()
    lead = store.get_lead(lead_id)
    if not lead:
        return f"Error: Lead '{lead_id}' not found."

    campaign = store.get_campaign(lead.campaign_id)
    if not campaign:
        return f"Error: Campaign '{lead.campaign_id}' not found."

    conversation = store.get_conversation(lead_id)
    conv_history = ""
    if conversation and conversation.messages:
        lines = []
        for msg in conversation.messages[-6:]:
            direction = "YOU SENT" if msg.direction == "outbound" else "THEY REPLIED"
            lines.append(f"[{direction} - {msg.timestamp[:10]}]\nSubject: {msg.subject}\n{msg.body}\n")
        conv_history = "\n---\n".join(lines)

    pitch_excerpt = campaign.pitch_deck_content[:3000] if campaign.pitch_deck_content else campaign.value_proposition
    knowledge_excerpt = (campaign.knowledge_content or "")[:4000]
    template = campaign.email_templates.get(email_type, "")

    conv_section = f"CONVERSATION HISTORY:\n{conv_history}" if conv_history else "No prior conversation."
    angle_section = f"CUSTOM ANGLE: {custom_angle}" if custom_angle else ""
    knowledge_section = f"APPROVED KNOWLEDGE:\n{knowledge_excerpt}" if knowledge_excerpt else "No knowledge base loaded."
    template_section = f"TEMPLATE GUIDANCE:\n{template}" if template else ""

    if email_type == "initial":
        compose_instruction = "Write the initial cold outreach email"
    elif email_type == "follow_up":
        compose_instruction = "Write a follow-up email"
    else:
        compose_instruction = "Write a reply to their response"

    if lead.lead_type.value == "investor":
        audience_note = "For investors: focus on market opportunity, traction, and team"
    else:
        audience_note = "For customers: focus on their specific pain points and how Solstice solves them"

    pain_str = ", ".join(lead.pain_points) or "unknown"

    context = f"""COMPOSE EMAIL for {email_type.upper()} outreach.

LEAD PROFILE:
  Name: {lead.first_name} {lead.last_name}
  Title: {lead.title}
  Company: {lead.company}
  Industry: {lead.industry}
  Company description: {lead.company_description}
  Pain points: {pain_str}
  Research notes: {lead.research_notes}
  Lead type: {lead.lead_type.value}
  Score: {lead.score}/100

CAMPAIGN: {campaign.name} ({campaign.campaign_type.value})
  Persona: {campaign.persona_name}
  Value proposition: {campaign.value_proposition}
  Target criteria: {campaign.target_criteria}
  Draft only: {campaign.draft_only}
  Approved attachments: {", ".join(campaign.approved_attachments) or "none"}

PITCH DECK CONTEXT:
{pitch_excerpt}

{conv_section}

{angle_section}

{knowledge_section}

{template_section}

INSTRUCTIONS:
- {compose_instruction}
- Personalize based on the lead's company, pain points, and industry
- Reference specific details from their company; avoid generic language
- {audience_note}
- Keep it concise (150-250 words for initial, shorter for follow-ups)
- Professional but warm tone; not salesy, not robotic
- Clear, low-friction CTA (e.g., "Would a 15-minute call next week work?")
- Do not use placeholder brackets like [Company]; use actual values
- Only reference facts present in the campaign, conversation history, or approved knowledge
- If the campaign is draft_only, outreach_send will create a draft instead of sending
- After composing, call outreach_send with the lead_id, subject, and body"""

    return context


def outreach_send(lead_id: str, subject: str, body: str) -> str:
    """Create a draft or send a composed email to a lead. Records history and schedules follow-up."""
    store = get_store()
    lead = store.get_lead(lead_id)
    if not lead:
        return f"Error: Lead '{lead_id}' not found."

    if lead.opted_out:
        return f"Error: Lead {lead.email} has opted out. Cannot contact."

    campaign = store.get_campaign(lead.campaign_id)
    if not campaign:
        return f"Error: Campaign '{lead.campaign_id}' not found."

    if not store.can_send_today():
        return "Error: Daily send limit reached (500 emails). Try again tomorrow."

    from ..gateway.channels.email_channel import EmailChannel

    email_config = {
        "email": campaign.mailbox or os.getenv("GATEWAY_EMAIL_ADDRESS", ""),
        "password": os.getenv("GATEWAY_EMAIL_PASSWORD", ""),
        "provider": os.getenv("GATEWAY_EMAIL_PROVIDER", "smtp"),
        "smtp_host": os.getenv("GATEWAY_EMAIL_SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": os.getenv("GATEWAY_EMAIL_SMTP_PORT", "587"),
        "graph_token": os.getenv("GATEWAY_EMAIL_GRAPH_TOKEN", ""),
        "graph_user": campaign.mailbox or os.getenv("GATEWAY_EMAIL_GRAPH_USER", ""),
    }

    channel = EmailChannel(email_config)
    if not channel.is_configured():
        return (
            "Error: Email not configured. Set mailbox auth via Graph token or SMTP credentials."
        )

    conversation = store.get_conversation(lead_id)
    if conversation and conversation.messages:
        original_subject = conversation.messages[0].subject
        if subject.startswith("Re:"):
            pass
        elif original_subject and not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"

    attachment_paths = store.resolve_attachment_paths(campaign.attachments_dir, campaign.approved_attachments)
    metadata = {
        "subject": subject,
        "mode": "draft" if campaign.draft_only else "send",
        "attachments": [str(p) for p in attachment_paths],
    }
    result = channel.send_message(lead.email, body, metadata=metadata)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        if "bounce" in error.lower() or "rejected" in error.lower():
            lead.stage = LeadStage.BOUNCED
            store.save_lead(lead)
            campaign.bounced += 1
            store.save_campaign(campaign)
        return f"Error contacting {lead.email}: {error}"

    mode = result.get("mode", metadata["mode"])
    msg = EmailMessage(direction="outbound", subject=subject, body=body)

    if not conversation:
        conversation = Conversation(lead_id=lead_id, campaign_id=lead.campaign_id)
    conversation.messages.append(msg)
    store.save_conversation(conversation)

    lead.emails_sent += 1
    lead.last_contacted = msg.timestamp
    if lead.stage == LeadStage.QUALIFIED:
        lead.stage = LeadStage.CONTACTED

    if campaign and lead.follow_up_count < lead.max_follow_ups:
        follow_up_idx = min(lead.follow_up_count, len(campaign.follow_up_days) - 1)
        days = campaign.follow_up_days[follow_up_idx]
        lead.next_follow_up = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    store.save_lead(lead)
    store.increment_sent()

    campaign.emails_sent += 1
    store.save_campaign(campaign)

    artifact = store.save_outbound_artifact(
        lead_id=lead_id,
        subject=subject,
        body=body,
        mode=mode,
        attachments=[p.name for p in attachment_paths],
        metadata={
            "recipient": lead.email,
            "draft_id": result.get("draft_id", ""),
            "web_link": result.get("web_link", ""),
        },
    )

    verb = "Draft created for" if mode == "draft" else "Email sent to"
    lines = [
        f"{verb} {lead.first_name} {lead.last_name} ({lead.email})",
        f"  Subject: {subject}",
        f"  Stage: {lead.stage.value}",
        f"  Follow-up: {lead.next_follow_up[:10] if lead.next_follow_up else 'none'}",
        f"  Attachments: {', '.join(p.name for p in attachment_paths) if attachment_paths else 'none'}",
        f"  Artifact: {artifact}",
    ]
    if result.get("web_link"):
        lines.append(f"  Outlook draft: {result['web_link']}")
    return "\n".join(lines)
