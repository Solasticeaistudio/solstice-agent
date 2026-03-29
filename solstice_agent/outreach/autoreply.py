"""
Outreach Autoreply
==================
Generate and send or draft safe reply emails using the configured LLM provider.
"""

import json
import re
from typing import Optional

from ..agent.personalities import resolve_personality
from .composer import outreach_compose, outreach_send
from .reply_triage import _pending_reply_leads, _classify_reply


def outreach_autoreply_safe(
    provider,
    campaign_id: str = "",
    limit: int = 10,
    personality_name: str = "outreach_war_room",
    temperature: float = 0.2,
    max_tokens: int = 1200,
    booking_link: str = "",
    booking_cta: str = "If helpful, you can grab a time here:",
    booking_label: str = "booking link",
) -> str:
    """
    Generate and dispatch safe reply drafts or sends for pending inbound replies.

    Campaign draft_only controls whether outreach_send creates drafts or sends mail.
    """
    pending = _pending_reply_leads(campaign_id=campaign_id)
    if not pending:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No pending replies found for {scope}."

    personality = resolve_personality(personality_name)
    processed = 0
    skipped = 0
    failed = 0
    escalated = 0
    lines = []

    for lead, body in pending[:max(limit, 0)]:
        triage = _classify_reply(body)
        if triage["intent"] == "demo_request" and booking_link:
            result = _send_demo_booking_reply(
                lead_id=lead.id,
                body=body,
                booking_link=booking_link,
                booking_cta=booking_cta,
                booking_label=booking_label,
            )
            processed += 1
            lines.append(
                f"PROCESSED {lead.first_name} {lead.last_name} ({lead.company}) "
                f"[demo_request]\n{result}"
            )
            continue

        if not triage["safe_to_auto_reply"]:
            escalated += 1
            lines.append(
                f"ESCALATE {lead.first_name} {lead.last_name} ({lead.company}) "
                f"[{triage['intent']}]: {triage['recommended_action']}"
            )
            continue

        context = outreach_compose(
            lead.id,
            email_type="reply",
            custom_angle=triage["custom_angle"],
        )
        prompt = (
            f"{context}\n\n"
            "Write the actual reply email.\n"
            "Return ONLY valid JSON with this shape:\n"
            "{\"subject\":\"...\",\"body\":\"...\"}\n"
            "Rules:\n"
            "- Keep it concise and executive-friendly\n"
            "- Answer the latest inbound message directly\n"
            "- Do not use markdown fences\n"
            "- Do not include any keys other than subject and body"
        )

        raw = _model_reply(
            provider=provider,
            system_prompt=personality.to_system_prompt(),
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        payload = _extract_email_json(raw)
        if not payload:
            failed += 1
            lines.append(
                f"FAILED {lead.first_name} {lead.last_name} ({lead.company}) "
                f"[{triage['intent']}]: invalid model output"
            )
            continue

        subject = (payload.get("subject") or "").strip()
        body_text = (payload.get("body") or "").strip()
        if not subject or not body_text:
            failed += 1
            lines.append(
                f"FAILED {lead.first_name} {lead.last_name} ({lead.company}) "
                f"[{triage['intent']}]: empty subject/body"
            )
            continue

        result = outreach_send(lead.id, subject, body_text)
        processed += 1
        lines.append(
            f"PROCESSED {lead.first_name} {lead.last_name} ({lead.company}) "
            f"[{triage['intent']}]\n{result}"
        )

    summary = [
        f"Safe autoreply processed: {processed}",
        f"Escalated: {escalated}",
        f"Failed: {failed}",
        f"Skipped: {skipped}",
    ]
    return "\n".join(summary + lines)


def _model_reply(provider, system_prompt: str, prompt: str, temperature: float, max_tokens: int) -> str:
    response = provider.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        tools=None,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response.text or "").strip()


def _extract_email_json(text: str) -> Optional[dict]:
    text = (text or "").strip()
    if not text:
        return None

    candidates = [text]
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates.extend(fenced)

    brace_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if brace_match:
        candidates.append(brace_match.group(1))

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "subject" in payload and "body" in payload:
            return payload
    return None


def _send_demo_booking_reply(
    lead_id: str,
    body: str,
    booking_link: str,
    booking_cta: str,
    booking_label: str,
) -> str:
    intro = "Thanks for the note. Happy to do a short walkthrough."
    if "next week" in (body or "").lower():
        intro = "Thanks for the note. Happy to do a short walkthrough next week."

    reply_body = (
        f"{intro}\n\n"
        f"{booking_cta} {booking_link}\n\n"
        f"If email is easier, feel free to send a couple of windows that work on your side "
        f"and I can coordinate from there."
    )
    subject = f"Re: {booking_label}"
    return outreach_send(lead_id, subject, reply_body)
