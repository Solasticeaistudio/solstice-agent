"""
Sender
======
Rate limiting and send window enforcement.
"""

import logging
from datetime import datetime, timezone

from .store import get_store

log = logging.getLogger("solstice.outreach.sender")

GLOBAL_DAILY_LIMIT = 500


def check_send_allowed(campaign_id: str = "") -> tuple:
    """Check if sending is currently allowed. Returns (allowed, reason)."""
    store = get_store()

    if not store.can_send_today(GLOBAL_DAILY_LIMIT):
        return False, f"Daily global limit reached ({GLOBAL_DAILY_LIMIT})"

    if campaign_id:
        campaign = store.get_campaign(campaign_id)
        if campaign:
            today_leads = store.list_leads(campaign_id=campaign_id)
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_sends = sum(
                1 for ld in today_leads
                if ld.last_contacted and ld.last_contacted[:10] == today_str
            )
            if today_sends >= campaign.daily_send_limit:
                return False, f"Campaign daily limit reached ({campaign.daily_send_limit})"

    return True, "OK"
