"""
Outreach Sync Queue
===================
Connector-ready exports for CRM and meeting handoff workflows.
"""

import httpx

from .models import LeadStage
from .store import get_store


def outreach_export_crm(campaign_id: str = "") -> str:
    store = get_store()
    records = _crm_records(store.list_leads(campaign_id=campaign_id or None), campaign_id)
    if isinstance(records, str):
        return records
    artifact = store.save_export_artifact(
        name=f"crm-export-{campaign_id or 'all'}",
        payload={"records": records},
        extension="json",
    )
    return f"CRM export created: {artifact}\n  Records: {len(records)}"


def outreach_export_meeting_queue(campaign_id: str = "") -> str:
    store = get_store()
    queue = _meeting_records(store, store.list_leads(campaign_id=campaign_id or None), campaign_id)
    if isinstance(queue, str):
        return queue
    artifact = store.save_export_artifact(
        name=f"meeting-queue-{campaign_id or 'all'}",
        payload={"records": queue},
        extension="json",
    )
    return f"Meeting queue export created: {artifact}\n  Records: {len(queue)}"


def outreach_push_crm(campaign_id: str = "", webhook_url: str = "") -> str:
    store = get_store()
    records = _crm_records(store.list_leads(campaign_id=campaign_id or None), campaign_id)
    if isinstance(records, str):
        return records
    if not webhook_url:
        return "Error: webhook_url is required."
    _post_json(webhook_url, {"records": records, "type": "crm_export", "campaign_id": campaign_id or ""})
    return f"CRM webhook push complete.\n  URL: {webhook_url}\n  Records: {len(records)}"


def outreach_push_meeting_queue(campaign_id: str = "", webhook_url: str = "") -> str:
    store = get_store()
    records = _meeting_records(store, store.list_leads(campaign_id=campaign_id or None), campaign_id)
    if isinstance(records, str):
        return records
    if not webhook_url:
        return "Error: webhook_url is required."
    _post_json(webhook_url, {"records": records, "type": "meeting_queue", "campaign_id": campaign_id or ""})
    return f"Meeting webhook push complete.\n  URL: {webhook_url}\n  Records: {len(records)}"


def _crm_records(leads, campaign_id: str):
    if not leads:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No leads found for {scope}."
    records = []
    for lead in leads:
        records.append(
            {
                "lead_id": lead.id,
                "campaign_id": lead.campaign_id,
                "stage": lead.stage.value,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "title": lead.title,
                "company": lead.company,
                "company_url": lead.company_url,
                "industry": lead.industry,
                "score": lead.score,
                "tags": lead.tags,
                "last_detected_intent": lead.last_detected_intent,
                "deferred_until": lead.deferred_until,
                "next_follow_up": lead.next_follow_up,
                "research_notes": lead.research_notes,
                "pipeline_notes": lead.pipeline_notes,
            }
        )
    return records


def _meeting_records(store, leads, campaign_id: str):
    if not leads:
        scope = f"campaign '{campaign_id}'" if campaign_id else "all campaigns"
        return f"No leads found for {scope}."
    queue = []
    for lead in leads:
        if "demo_requested" not in lead.tags and lead.stage != LeadStage.CONVERTED:
            continue
        conversation = store.get_conversation(lead.id)
        last_inbound = ""
        if conversation and conversation.messages:
            for msg in reversed(conversation.messages):
                if msg.direction == "inbound":
                    last_inbound = msg.body
                    break
        queue.append(
            {
                "lead_id": lead.id,
                "campaign_id": lead.campaign_id,
                "name": f"{lead.first_name} {lead.last_name}".strip(),
                "email": lead.email,
                "company": lead.company,
                "title": lead.title,
                "stage": lead.stage.value,
                "tags": lead.tags,
                "last_detected_intent": lead.last_detected_intent,
                "last_inbound": last_inbound,
                "research_notes": lead.research_notes,
                "pipeline_notes": lead.pipeline_notes,
            }
        )
    return queue


def _post_json(webhook_url: str, payload: dict):
    with httpx.Client(timeout=20.0) as client:
        response = client.post(webhook_url, json=payload)
        response.raise_for_status()
