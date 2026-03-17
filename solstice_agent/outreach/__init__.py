"""
Outreach System
===============
Autonomous email outreach for investors and customers.

Keep package imports lightweight so higher-level modules can import
personality definitions without triggering the whole outreach stack.
"""

from importlib import import_module

__all__ = [
    "register_outreach_tools",
    "init_outreach",
    "get_orchestrator",
    "load_seed_bundle",
    "triage_reply",
    "outreach_prepare_reply_batch",
    "outreach_reply_review_queue",
    "outreach_pipeline_snapshot",
    "outreach_autoreply_safe",
    "outreach_analytics",
    "outreach_next_best_actions",
    "outreach_export_crm",
    "outreach_export_meeting_queue",
    "Lead",
    "Campaign",
    "LeadType",
    "CampaignStatus",
]


def __getattr__(name):
    if name == "register_outreach_tools":
        return import_module(".tools", __name__).register_outreach_tools
    if name in {"init_outreach", "get_orchestrator"}:
        module = import_module(".orchestrator", __name__)
        return getattr(module, name)
    if name in {"Lead", "Campaign", "LeadType", "CampaignStatus"}:
        module = import_module(".models", __name__)
        return getattr(module, name)
    if name == "load_seed_bundle":
        return import_module(".seed_loader", __name__).load_seed_bundle
    if name in {"triage_reply", "outreach_prepare_reply_batch", "outreach_reply_review_queue", "outreach_pipeline_snapshot"}:
        module = import_module(".reply_triage", __name__)
        return getattr(module, name)
    if name == "outreach_autoreply_safe":
        return import_module(".autoreply", __name__).outreach_autoreply_safe
    if name in {"outreach_analytics", "outreach_next_best_actions"}:
        module = import_module(".analytics", __name__)
        return getattr(module, name)
    if name in {"outreach_export_crm", "outreach_export_meeting_queue"}:
        module = import_module(".sync_queue", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
