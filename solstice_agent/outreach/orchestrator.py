"""
Orchestrator
============
Autonomous campaign execution via the Scheduler.
Schedules 4 recurring jobs: inbox check, follow-up, prospecting, send queue.
"""

import logging
from typing import Optional

from ..agent.scheduler import get_scheduler
from .store import get_store
from .models import CampaignStatus

log = logging.getLogger("solstice.outreach.orchestrator")

_orchestrator: Optional["OutreachOrchestrator"] = None


class OutreachOrchestrator:

    INBOX_CHECK_SCHEDULE = "every 15m"
    FOLLOW_UP_SCHEDULE = "every 1h"
    PROSPECT_SCHEDULE = "every 6h"
    SEND_QUEUE_SCHEDULE = "every 30m"

    def __init__(self):
        self._inbox_job_id: str = ""
        self._follow_up_job_id: str = ""
        self._prospect_job_id: str = ""
        self._send_job_id: str = ""

    def start_campaign(self, campaign_id: str) -> str:
        store = get_store()
        campaign = store.get_campaign(campaign_id)
        if not campaign:
            return f"Error: Campaign '{campaign_id}' not found."

        if campaign.status == CampaignStatus.ACTIVE:
            return f"Campaign '{campaign.name}' is already active."

        campaign.status = CampaignStatus.ACTIVE
        store.save_campaign(campaign)
        self._ensure_jobs_scheduled()

        return (
            f"Campaign '{campaign.name}' activated.\n"
            f"Autonomous jobs scheduled:\n"
            f"  - Inbox check: {self.INBOX_CHECK_SCHEDULE}\n"
            f"  - Follow-up scan: {self.FOLLOW_UP_SCHEDULE}\n"
            f"  - Prospecting: {self.PROSPECT_SCHEDULE}\n"
            f"  - Send queue: {self.SEND_QUEUE_SCHEDULE}"
        )

    def pause_campaign(self, campaign_id: str) -> str:
        store = get_store()
        campaign = store.get_campaign(campaign_id)
        if not campaign:
            return f"Error: Campaign '{campaign_id}' not found."

        campaign.status = CampaignStatus.PAUSED
        store.save_campaign(campaign)

        active = store.list_campaigns(status=CampaignStatus.ACTIVE)
        if not active:
            self._remove_all_jobs()

        return f"Campaign '{campaign.name}' paused."

    def _ensure_jobs_scheduled(self):
        scheduler = get_scheduler()
        if not scheduler:
            log.warning("Scheduler not initialized. Outreach jobs won't run automatically.")
            return

        existing_jobs = scheduler.list_jobs()
        existing_queries = {j["query"] for j in existing_jobs}

        jobs = [
            (
                self.INBOX_CHECK_SCHEDULE,
                "Check the outreach inbox for new replies using outreach_check_inbox. "
                "If there are replies that need responses, use outreach_compose with email_type='reply' "
                "for each lead, then outreach_send to respond.",
            ),
            (
                self.FOLLOW_UP_SCHEDULE,
                "Check for outreach leads due for follow-up using outreach_follow_ups_due. "
                "For each lead due, use outreach_compose with email_type='follow_up', "
                "then outreach_send to deliver the follow-up.",
            ),
            (
                self.PROSPECT_SCHEDULE,
                "Run outreach_prospect_auto for all active campaigns. "
                "Search for new leads, research them, qualify them, and add qualified ones.",
            ),
            (
                self.SEND_QUEUE_SCHEDULE,
                "Check for qualified outreach leads using outreach_send_queue. "
                "For each one, use outreach_compose then outreach_send for the initial email.",
            ),
        ]

        for schedule, query in jobs:
            if query not in existing_queries:
                try:
                    job = scheduler.add_job(schedule, query)
                    log.info(f"Scheduled outreach job: {job['id']} ({schedule})")
                except Exception as e:
                    log.error(f"Failed to schedule job ({schedule}): {e}")

    def _remove_all_jobs(self):
        scheduler = get_scheduler()
        if not scheduler:
            return
        for job_id in [self._inbox_job_id, self._follow_up_job_id,
                       self._prospect_job_id, self._send_job_id]:
            if job_id:
                scheduler.remove_job(job_id)


def get_orchestrator() -> OutreachOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OutreachOrchestrator()
    return _orchestrator


def init_outreach():
    """Initialize outreach system. Call at startup."""
    get_store()
    get_orchestrator()
    log.info("Outreach system initialized")
