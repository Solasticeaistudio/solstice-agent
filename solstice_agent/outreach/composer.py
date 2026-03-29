"""
Email Composer
==============
Assembles personalization context for Sol to compose outreach emails.
Handles draft creation or sending plus conversation recording.
"""

import logging
import os
import html
from datetime import datetime, timedelta, timezone

from .store import get_store
from .models import LeadStage, EmailMessage, Conversation

log = logging.getLogger("solstice.outreach.composer")

DEFAULT_SIGNATURE_NAME = os.environ.get("SOL_SIGNATURE_NAME", "Solstice Studio")
DEFAULT_SIGNATURE_TITLE = os.environ.get("SOL_SIGNATURE_TITLE", "Founder | Solstice Studio")
DEFAULT_SIGNATURE_GROUP = os.environ.get("SOL_SIGNATURE_GROUP", "Solstice Studio")
DEFAULT_SIGNATURE_TAGLINE = os.environ.get("SOL_SIGNATURE_TAGLINE", "Local-first AI agents")
DEFAULT_SIGNATURE_WEBSITE = os.environ.get("SOL_SIGNATURE_WEBSITE", "https://solsticestudio.ai")
DEFAULT_SIGNATURE_EMAIL = os.environ.get("SOL_SIGNATURE_EMAIL", "hello@solsticestudio.ai")
DEFAULT_SIGNATURE_LOGO_URL = os.environ.get("SOL_SIGNATURE_LOGO_URL", "https://solsticestudio.ai/static/ssi-logo.png")


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
    effective_angle = custom_angle
    if email_type == "follow_up" and not effective_angle:
        effective_angle = _derive_follow_up_angle(lead)

    angle_section = f"CUSTOM ANGLE: {effective_angle}" if effective_angle else ""
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
  Last detected intent: {lead.last_detected_intent or "unknown"}
  Tags: {", ".join(lead.tags) or "none"}
  Deferred until: {lead.deferred_until[:10] if lead.deferred_until else "none"}

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
    provider = (email_config.get("provider") or "").lower()
    metadata = {
        "subject": subject,
        "mode": "draft" if campaign.draft_only else "send",
        "attachments": [str(p) for p in attachment_paths],
    }
    plain_body = _apply_signature(body)
    body_to_send = plain_body
    stored_body = plain_body
    if provider in {"graph", "outlook"}:
        metadata["content_type"] = "HTML"
        body_to_send = _render_html_email(body)
        stored_body = _apply_signature(body)
    result = channel.send_message(lead.email, body_to_send, metadata=metadata)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        if "bounce" in error.lower() or "rejected" in error.lower():
            lead.stage = LeadStage.BOUNCED
            store.save_lead(lead)
            campaign.bounced += 1
            store.save_campaign(campaign)
        return f"Error contacting {lead.email}: {error}"

    mode = result.get("mode", metadata["mode"])
    msg = EmailMessage(direction="outbound", subject=subject, body=stored_body)

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
        body=stored_body,
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


def _signature_settings() -> dict:
    return {
        "name": os.getenv("SOLSTICE_OUTREACH_SIGNATURE_NAME", DEFAULT_SIGNATURE_NAME),
        "title": os.getenv("SOLSTICE_OUTREACH_SIGNATURE_TITLE", DEFAULT_SIGNATURE_TITLE),
        "group": os.getenv("SOLSTICE_OUTREACH_SIGNATURE_GROUP", DEFAULT_SIGNATURE_GROUP),
        "tagline": os.getenv("SOLSTICE_OUTREACH_SIGNATURE_TAGLINE", DEFAULT_SIGNATURE_TAGLINE),
        "website": os.getenv("SOLSTICE_OUTREACH_SIGNATURE_WEBSITE", DEFAULT_SIGNATURE_WEBSITE),
        "email": os.getenv("SOLSTICE_OUTREACH_SIGNATURE_EMAIL", DEFAULT_SIGNATURE_EMAIL),
        "logo_url": os.getenv("SOLSTICE_OUTREACH_SIGNATURE_LOGO_URL", DEFAULT_SIGNATURE_LOGO_URL),
    }


def _apply_signature(body: str) -> str:
    text = (body or "").strip()
    if not text:
        return _render_plain_signature()
    if _body_has_signature(text):
        return text
    return f"{text}\n\n{_render_plain_signature()}"


def _body_has_signature(body: str) -> bool:
    lowered = (body or "").lower()
    markers = (
        "solsticestudio.ai",
        DEFAULT_SIGNATURE_EMAIL.lower(),
        DEFAULT_SIGNATURE_NAME.lower(),
        DEFAULT_SIGNATURE_GROUP.lower(),
    )
    return any(marker in lowered for marker in markers)


def _render_plain_signature() -> str:
    settings = _signature_settings()
    lines = [
        "Best,",
        settings["name"],
        settings["title"],
        "",
        settings["group"],
        settings["tagline"],
        settings["website"],
        settings["email"],
    ]
    return "\n".join(lines)


def _render_html_email(body: str) -> str:
    settings = _signature_settings()
    safe_body = html.escape((body or "").strip())
    body_html = "<br>".join(safe_body.splitlines()) if safe_body else ""
    logo_html = (
        f"<img src=\"{html.escape(settings['logo_url'])}\" alt=\"Solstice Strategic Intelligence\" "
        f"style=\"width:68px;height:68px;object-fit:contain;display:block;border-radius:12px;\">"
    ) if settings["logo_url"] else ""
    website = html.escape(settings["website"])
    email_address = html.escape(settings["email"])
    signature_html = (
        "<div style=\"margin-top:24px;font-size:15px;color:#111827;\">Best,</div>"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" "
        "style=\"margin-top:12px;border-collapse:collapse;\">"
        "<tr>"
        "<td style=\"vertical-align:top;padding-right:16px;\">"
        f"{logo_html}"
        "</td>"
        "<td style=\"vertical-align:top;border-left:2px solid #d1d5db;padding-left:16px;\">"
        f"<div style=\"font-size:16px;font-weight:700;color:#111827;\">{html.escape(settings['name'])}</div>"
        f"<div style=\"font-size:13px;color:#4b5563;margin-top:2px;\">{html.escape(settings['title'])}</div>"
        f"<div style=\"font-size:13px;font-weight:700;color:#111827;margin-top:12px;\">{html.escape(settings['group'])}</div>"
        f"<div style=\"font-size:13px;color:#4b5563;margin-top:2px;\">{html.escape(settings['tagline'])}</div>"
        f"<div style=\"font-size:13px;margin-top:10px;\"><a href=\"{website}\" style=\"color:#1d4ed8;text-decoration:none;\">Strategic Intelligence Engine</a></div>"
        f"<div style=\"font-size:13px;margin-top:4px;\"><a href=\"mailto:{email_address}\" style=\"color:#1d4ed8;text-decoration:none;\">{email_address}</a></div>"
        "</td>"
        "</tr>"
        "</table>"
    )
    return (
        "<div style=\"font-family:Arial,sans-serif;font-size:15px;line-height:1.6;color:#111827;\">"
        f"<div>{body_html}</div>"
        f"{signature_html}"
        "</div>"
    )


def outreach_prepare_draft_batch(
    campaign_id: str,
    email_type: str = "initial",
    limit: int = 10,
    stage: str = "qualified",
    custom_angle: str = "",
) -> str:
    """Prepare compose artifacts for a batch of leads so drafts can be generated systematically."""
    store = get_store()
    campaign = store.get_campaign(campaign_id)
    if not campaign:
        return f"Error: Campaign '{campaign_id}' not found."

    try:
        stage_filter = LeadStage(stage) if stage else None
    except ValueError:
        valid = ", ".join(s.value for s in LeadStage)
        return f"Error: stage must be one of: {valid}"

    leads = store.list_leads(campaign_id=campaign_id, stage=stage_filter) if stage_filter else store.list_leads(campaign_id=campaign_id)
    eligible = []
    for lead in leads:
        if lead.opted_out:
            continue
        if email_type == "initial" and lead.emails_sent > 0:
            continue
        eligible.append(lead)

    if not eligible:
        return f"No eligible leads found for campaign '{campaign.name}' ({email_type}, stage={stage_filter.value if stage_filter else 'any'})."

    artifacts = []
    for lead in eligible[:max(limit, 0)]:
        per_lead_angle = custom_angle
        if email_type == "follow_up" and not per_lead_angle:
            per_lead_angle = _derive_follow_up_angle(lead)

        context = outreach_compose(lead.id, email_type=email_type, custom_angle=per_lead_angle)
        artifact = store.save_compose_artifact(
            lead_id=lead.id,
            email_type=email_type,
            context=context,
            metadata={
                "campaign_id": campaign_id,
                "campaign_name": campaign.name,
                "lead_email": lead.email,
                "company": lead.company,
                "stage": lead.stage.value,
                "custom_angle": per_lead_angle,
            },
        )
        artifacts.append((lead, artifact))

    lines = [
        f"Prepared {len(artifacts)} compose artifacts for '{campaign.name}'",
        f"  Email type: {email_type}",
        f"  Stage filter: {stage_filter.value if stage_filter else 'any'}",
    ]
    for lead, artifact in artifacts:
        lines.append(
            f"  {lead.first_name} {lead.last_name} ({lead.company})\n"
            f"    Lead ID: {lead.id}\n"
            f"    Artifact: {artifact}"
        )
    return "\n".join(lines)


def _derive_follow_up_angle(lead) -> str:
    if lead.deferred_until:
        return (
            "This lead previously deferred timing. Keep the follow-up low-pressure, "
            "acknowledge timing, and re-open the conversation only if it remains relevant."
        )
    if "needs_info" in lead.tags or lead.last_detected_intent == "interested_needs_more_info":
        return (
            "This lead asked for more information. Follow up with one concrete example or approved sample output angle, "
            "not a generic nudge."
        )
    if "routed" in lead.tags or lead.last_detected_intent == "routing_referral":
        return (
            "This lead previously routed the conversation. Follow up in a way that is easy to forward internally "
            "and references the routing context."
        )
    if "objection" in lead.tags or lead.last_detected_intent == "challenge_objection":
        return (
            "This lead raised skepticism or an objection. Follow up by clarifying the differentiation calmly and directly "
            "without sounding defensive."
        )
    if "pricing_requested" in lead.tags:
        return (
            "This lead previously asked about pricing. Do not improvise new pricing; follow up only if there is approved "
            "commercial context or to move toward a scoped conversation."
        )
    if "demo_requested" in lead.tags:
        return (
            "This lead previously showed demo interest. Follow up with a clear next step toward scheduling or confirming the demo."
        )
    return ""
