"""
Echo Bridge
===========
Routes outreach sends through the EchoDelivery authenticity pipeline
instead of raw SMTP.

Every message sent via this bridge must pass Echo's 8-dimension
authenticity proof (threshold 0.62) before it transmits. Hard blocks,
suppression checks, domain reputation, and send scheduling are all
enforced server-side.

Usage:
    from .echo_bridge import send_via_echo, preflight_proof, is_echo_available

    # Check before sending
    ok, reason = preflight_proof(to, subject, body)
    if not ok:
        log.warning("Echo blocked: %s", reason)
        return

    # Send through Echo
    result = send_via_echo(to=lead.email, subject=subject, body_text=body)
"""

import logging
import os
from typing import Optional, Tuple

import requests

log = logging.getLogger("solstice.outreach.echo_bridge")

ECHO_URL = os.getenv("ECHO_DELIVERY_URL", "http://localhost:5000")
ECHO_TIMEOUT_SYNC  = 35   # seconds — /send/sync
ECHO_TIMEOUT_ASYNC = 10   # seconds — /send (queued)
ECHO_TIMEOUT_PROOF = 10   # seconds — /proof


def is_echo_available() -> bool:
    """Quick health check — returns True if Echo backend is reachable."""
    try:
        r = requests.get(f"{ECHO_URL}/api/echo/delivery/queue/status", timeout=3)
        return r.ok
    except Exception:
        return False


def send_via_echo(
    to: str,
    from_addr: str,
    subject: str,
    body_text: str,
    body_html: str = "",
    trigger_event: str = "",
    trigger_recency_days: float = 999,
    relationship_hints: Optional[dict] = None,
    value_offer: str = "",
    recipient_tz: str = "+00:00",
    urgent: bool = False,
    sync: bool = True,
    sender_id: str = "solstice-agent",
    recipient_id: str = "",
) -> dict:
    """
    Route an outreach email through Echo's authenticity pipeline.

    Args:
        to:                    Recipient email address
        from_addr:             Sender email address
        subject:               Email subject
        body_text:             Plain-text body
        body_html:             HTML body (optional)
        trigger_event:         "why now" event (e.g. "series_b_announcement")
        trigger_recency_days:  Days since trigger (lower = more relevant)
        relationship_hints:    {"met_at": "SaaStr", "mutual": ["Alex"]}
        value_offer:           Concrete offer in ≤200 chars
        recipient_tz:          UTC offset string e.g. "-05:00"
        urgent:                Skip time-window constraint if True
        sync:                  Wait for result (True) or return request_id (False)
        sender_id:             Identifier for the sender (for Mnemosyne)
        recipient_id:          Identifier for the recipient (defaults to `to`)

    Returns:
        Dict with keys: success, request_id, sent_at, channel, error, stage_failed, authenticity
        Raises requests.HTTPError on non-2xx response.
    """
    endpoint = f"{ECHO_URL}/api/echo/delivery/{'send/sync' if sync else 'send'}"
    payload = {
        "recipient_address":    to,
        "sender_address":       from_addr,
        "channel":              "email",
        "subject":              subject,
        "body_text":            body_text,
        "body_html":            body_html,
        "trigger_event":        trigger_event,
        "trigger_recency_days": trigger_recency_days,
        "relationship_hints":   relationship_hints or {},
        "value_offer":          value_offer,
        "recipient_tz":         recipient_tz,
        "urgent":               urgent,
        "sender_id":            sender_id,
        "recipient_id":         recipient_id or to,
    }

    timeout = ECHO_TIMEOUT_SYNC if sync else ECHO_TIMEOUT_ASYNC
    log.debug("Echo send -> %s (%s)", to, "sync" if sync else "async")

    r = requests.post(endpoint, json=payload, timeout=timeout)

    if r.status_code in (200, 202, 422):
        result = r.json()
        if not result.get("success", True):
            log.warning(
                "Echo blocked send to %s at stage '%s': %s",
                to, result.get("stage_failed"), result.get("error"),
            )
        return result

    r.raise_for_status()
    return r.json()


def preflight_proof(
    to: str,
    subject: str,
    body_text: str,
    from_addr: str = "outreach@solsticestudio.ai",
    trigger_event: str = "",
    trigger_recency_days: float = 999,
    relationship_hints: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Run Echo's authenticity proof without sending.
    Returns (allowed: bool, reason: str).

    Use as a gate before any send — if Echo is down, defaults to allowing
    the send so Echo unavailability doesn't break campaigns.
    """
    try:
        r = requests.post(
            f"{ECHO_URL}/api/echo/delivery/proof",
            json={
                "recipient_address":    to,
                "sender_address":       from_addr,
                "channel":              "email",
                "subject":              subject,
                "body_text":            body_text,
                "trigger_event":        trigger_event,
                "trigger_recency_days": trigger_recency_days,
                "relationship_hints":   relationship_hints or {},
            },
            timeout=ECHO_TIMEOUT_PROOF,
        )
        d = r.json()

        if d.get("hard_blocked"):
            return False, d.get("block_reason") or "Hard blocked"

        if not d.get("passed"):
            score = d.get("calibrated_composite", 0)
            threshold = d.get("threshold", 0.62)
            return False, f"Authenticity score {score:.2f} below threshold {threshold}"

        return True, "OK"

    except requests.Timeout:
        log.warning("Echo proof timed out for %s — allowing send", to)
        return True, "Echo timeout — allowed"
    except Exception as e:
        log.warning("Echo proof unavailable (%s) — allowing send", e)
        return True, f"Echo unavailable — allowed"


def ingest_event(
    message_id: str,
    event_type: str,
    recipient_id: str,
    sender_id: str = "solstice-agent",
    channel: str = "email",
    metadata: Optional[dict] = None,
) -> bool:
    """
    Record a delivery event (open, reply, bounce, etc.) so Echo's
    EngagementTracker and Mnemosyne feedback loop stay current.

    event_type options:
        opened, replied, link_clicked,
        bounced_soft, bounced_hard,
        spam_complaint, unsubscribed
    """
    try:
        r = requests.post(
            f"{ECHO_URL}/api/echo/delivery/event/{message_id}",
            json={
                "event_type":   event_type,
                "recipient_id": recipient_id,
                "sender_id":    sender_id,
                "channel":      channel,
                "metadata":     metadata or {},
            },
            timeout=5,
        )
        return r.ok
    except Exception as e:
        log.warning("Echo event ingest failed: %s", e)
        return False


def suppress_address(address: str, reason: str = "campaign") -> bool:
    """Add an address to Echo's suppression list."""
    try:
        r = requests.post(
            f"{ECHO_URL}/api/echo/delivery/suppress",
            json={"address": address, "reason": reason},
            timeout=5,
        )
        return r.ok
    except Exception as e:
        log.warning("Echo suppress failed: %s", e)
        return False


def format_result(result: dict) -> str:
    """
    Convert a DeliveryResult dict into a one-line status string
    suitable for logging or Sol's tool response.
    """
    if result.get("status") == "queued":
        return f"Queued. request_id={result.get('request_id')}"

    if result.get("success"):
        ch = result.get("channel", {})
        return (
            f"Sent. provider={ch.get('provider')} "
            f"message_id={ch.get('message_id')} "
            f"sent_at={result.get('sent_at')}"
        )

    auth = result.get("authenticity", {})
    score_str = f"score={auth.get('score', '?'):.2f}" if auth else ""
    return (
        f"Blocked at '{result.get('stage_failed')}': "
        f"{result.get('error')} {score_str}".strip()
    )
