"""
Outreach Seed Loader
====================
Load campaign and lead seed payloads into the outreach store.
"""

import json
from pathlib import Path
from typing import Optional

from .models import Campaign, Lead
from .store import OutreachStore


def load_seed_bundle(
    campaign_seed_path: str,
    leads_seed_path: str,
    store_root: Optional[str] = None,
    replace: bool = False,
) -> str:
    """
    Load a campaign seed and associated lead seeds into the outreach store.

    Args:
        campaign_seed_path: Path to a single campaign JSON object.
        leads_seed_path: Path to a JSON array of leads for that campaign.
        store_root: Optional override for the outreach store root.
        replace: If True, overwrite an existing campaign or lead with the same id/email.
    """
    store = OutreachStore(root=store_root)

    campaign_payload = _read_json_object(campaign_seed_path)
    leads_payload = _read_json_array(leads_seed_path)

    campaign = Campaign.from_dict(campaign_payload)
    existing_campaign = store.get_campaign(campaign.id)
    if existing_campaign and not replace:
        raise ValueError(
            f"Campaign '{campaign.id}' already exists. Pass replace=True to overwrite it."
        )
    store.save_campaign(campaign)

    added = 0
    updated = 0
    skipped = 0

    for item in leads_payload:
        lead = Lead.from_dict(item)
        lead.campaign_id = campaign.id

        existing_by_id = store.get_lead(lead.id) if lead.id else None
        existing_by_email = store.get_lead_by_email(lead.email) if lead.email else None
        existing = existing_by_id or existing_by_email

        if existing and not replace:
            skipped += 1
            continue

        if existing and replace:
            lead.id = existing.id
            store.save_lead(lead)
            updated += 1
            continue

        store.save_lead(lead)
        added += 1

    return (
        f"Loaded campaign '{campaign.name}' ({campaign.id})\n"
        f"  Store: {store.root}\n"
        f"  Leads added: {added}\n"
        f"  Leads updated: {updated}\n"
        f"  Leads skipped: {skipped}"
    )


def _read_json_object(path: str) -> dict:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return data


def _read_json_array(path: str) -> list:
    data = _read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array at {path}")
    return data


def _read_json(path: str):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))
