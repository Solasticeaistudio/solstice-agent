"""
Outreach System
===============
Autonomous email outreach for investors and customers.
Prospect, pitch, send, track replies, and follow up — all on autopilot.
"""
from .tools import register_outreach_tools
from .orchestrator import init_outreach, get_orchestrator
from .models import Lead, Campaign, LeadType, CampaignStatus

__all__ = [
    "register_outreach_tools",
    "init_outreach",
    "get_orchestrator",
    "Lead",
    "Campaign",
    "LeadType",
    "CampaignStatus",
]
