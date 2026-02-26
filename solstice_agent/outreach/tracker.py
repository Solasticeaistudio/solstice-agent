"""
Tracker
=======
Inbox monitoring for outreach replies. Matches replies to leads, detects opt-outs.
"""

import logging
import os
import re

from .store import get_store
from .models import LeadStage, EmailMessage, Conversation

log = logging.getLogger("solstice.outreach.tracker")

OPT_OUT_PATTERNS = [
    r'\bunsubscribe\b',
    r'\bremove me\b',
    r'\bstop (emailing|contacting)\b',
    r'\bopt.?out\b',
    r'\bno thanks\b.*\bdon.?t contact\b',
    r'\bnot interested\b.*\bplease (stop|remove)\b',
]


def check_inbox_for_replies() -> str:
    """Poll inbox for replies to outreach emails. Match to leads, detect opt-outs."""
    from ..gateway.channels.email_channel import EmailChannel

    email_config = {
        "email": os.getenv("GATEWAY_EMAIL_ADDRESS", ""),
        "password": os.getenv("GATEWAY_EMAIL_PASSWORD", ""),
        "imap_host": os.getenv("GATEWAY_EMAIL_IMAP_HOST", "imap.gmail.com"),
    }

    channel = EmailChannel(email_config)
    if not channel.is_configured():
        return "Email channel not configured."

    # Allow all senders for outreach monitoring
    channel._allowed = set()
    messages = channel.poll_inbox(folder="INBOX", unseen_only=True, limit=20)

    if not messages:
        return "No new replies found."

    store = get_store()
    new_replies = []
    opt_outs = []

    for msg in messages:
        sender_email = msg.sender_id.lower()

        lead = store.get_lead_by_email(sender_email)
        if not lead:
            continue

        body_lower = msg.text.lower()
        is_opt_out = any(re.search(p, body_lower) for p in OPT_OUT_PATTERNS)

        if is_opt_out:
            lead.opted_out = True
            lead.stage = LeadStage.LOST
            store.save_lead(lead)

            campaign = store.get_campaign(lead.campaign_id)
            if campaign:
                campaign.opted_out += 1
                store.save_campaign(campaign)

            opt_outs.append(f"{lead.first_name} {lead.last_name} ({lead.email})")
            continue

        # Record reply
        email_msg = EmailMessage(
            direction="inbound",
            subject=msg.channel_metadata.get("subject", ""),
            body=msg.text,
            message_id=msg.channel_metadata.get("message_id", ""),
        )

        conversation = store.get_conversation(lead.id)
        if not conversation:
            conversation = Conversation(lead_id=lead.id, campaign_id=lead.campaign_id)
        conversation.messages.append(email_msg)
        store.save_conversation(conversation)

        # Update lead state
        lead.emails_received += 1
        lead.last_reply = email_msg.timestamp
        lead.next_follow_up = ""  # Cancel pending follow-up
        if lead.stage in (LeadStage.CONTACTED, LeadStage.QUALIFIED):
            lead.stage = LeadStage.REPLIED
        elif lead.stage == LeadStage.REPLIED:
            lead.stage = LeadStage.ENGAGED
        store.save_lead(lead)

        campaign = store.get_campaign(lead.campaign_id)
        if campaign:
            campaign.replies_received += 1
            store.save_campaign(campaign)

        new_replies.append(
            f"Reply from {lead.first_name} {lead.last_name} ({lead.email}) "
            f"[{lead.company}]:\n  {msg.text[:200]}..."
        )

    parts = []
    if new_replies:
        parts.append(f"NEW REPLIES ({len(new_replies)}):\n" + "\n\n".join(new_replies))
    if opt_outs:
        parts.append(f"OPT-OUTS ({len(opt_outs)}):\n" + "\n".join(opt_outs))
    if not parts:
        return "Checked inbox. No outreach-related replies found."

    return "\n\n".join(parts)


def get_pending_replies() -> str:
    """List leads that have replied but haven't been responded to yet."""
    store = get_store()
    replied_leads = store.list_leads(stage=LeadStage.REPLIED)
    engaged_leads = store.list_leads(stage=LeadStage.ENGAGED)

    needs_response = []
    for lead in replied_leads + engaged_leads:
        conversation = store.get_conversation(lead.id)
        if conversation and conversation.messages:
            last_msg = conversation.messages[-1]
            if last_msg.direction == "inbound":
                needs_response.append(
                    f"{lead.first_name} {lead.last_name} ({lead.email}) [{lead.company}]\n"
                    f"  Last reply: {last_msg.body[:150]}...\n"
                    f"  Lead ID: {lead.id}"
                )

    if not needs_response:
        return "No pending replies need a response."

    return f"Leads awaiting response ({len(needs_response)}):\n\n" + "\n\n".join(needs_response)
