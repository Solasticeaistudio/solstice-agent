"""
Outreach Store
==============
Persistent JSON storage for leads, campaigns, conversations, and metrics.

Storage layout:
    ~/.solstice-agent/outreach/
        campaigns.json
        leads.json
        conversations/{lead_id}.json
        metrics/{YYYY-MM-DD}.json
        pitch_decks/{filename}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .models import Lead, Campaign, Conversation, DailyMetrics, LeadStage, CampaignStatus

log = logging.getLogger("solstice.outreach.store")

_DEFAULT_ROOT = Path.home() / ".solstice-agent" / "outreach"


class OutreachStore:

    def __init__(self, root: Optional[str] = None):
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.campaigns_path = self.root / "campaigns.json"
        self.leads_path = self.root / "leads.json"
        self.conversations_dir = self.root / "conversations"
        self.metrics_dir = self.root / "metrics"
        self.pitch_decks_dir = self.root / "pitch_decks"
        self.drafts_dir = self.root / "drafts"

        for d in [self.root, self.conversations_dir, self.metrics_dir, self.pitch_decks_dir, self.drafts_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self._campaigns: Dict[str, Campaign] = self._load_campaigns()
        self._leads: Dict[str, Lead] = self._load_leads()

        log.info(f"OutreachStore: {len(self._campaigns)} campaigns, {len(self._leads)} leads")

    # --- Campaigns ---

    def save_campaign(self, campaign: Campaign) -> Campaign:
        campaign.updated_at = datetime.now(timezone.utc).isoformat()
        self._campaigns[campaign.id] = campaign
        self._persist_campaigns()
        return campaign

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        return self._campaigns.get(campaign_id)

    def list_campaigns(self, status: Optional[CampaignStatus] = None) -> List[Campaign]:
        campaigns = list(self._campaigns.values())
        if status:
            campaigns = [c for c in campaigns if c.status == status]
        return campaigns

    def delete_campaign(self, campaign_id: str) -> bool:
        if campaign_id in self._campaigns:
            del self._campaigns[campaign_id]
            self._persist_campaigns()
            return True
        return False

    # --- Leads ---

    def save_lead(self, lead: Lead) -> Lead:
        lead.updated_at = datetime.now(timezone.utc).isoformat()
        self._leads[lead.id] = lead
        self._persist_leads()
        return lead

    def get_lead(self, lead_id: str) -> Optional[Lead]:
        return self._leads.get(lead_id)

    def get_lead_by_email(self, email: str) -> Optional[Lead]:
        email_lower = email.lower()
        for lead in self._leads.values():
            if lead.email.lower() == email_lower:
                return lead
        return None

    def list_leads(
        self,
        campaign_id: Optional[str] = None,
        stage: Optional[LeadStage] = None,
        lead_type: Optional[str] = None,
    ) -> List[Lead]:
        leads = list(self._leads.values())
        if campaign_id:
            leads = [ld for ld in leads if ld.campaign_id == campaign_id]
        if stage:
            leads = [ld for ld in leads if ld.stage == stage]
        if lead_type:
            leads = [ld for ld in leads if ld.lead_type.value == lead_type]
        return leads

    def leads_needing_follow_up(self) -> List[Lead]:
        now = datetime.now(timezone.utc).isoformat()
        results = []
        for lead in self._leads.values():
            if (lead.next_follow_up
                    and lead.next_follow_up <= now
                    and lead.stage in (LeadStage.CONTACTED, LeadStage.ENGAGED)
                    and not lead.opted_out
                    and lead.follow_up_count < lead.max_follow_ups):
                results.append(lead)
        return results

    def delete_lead(self, lead_id: str) -> bool:
        if lead_id in self._leads:
            del self._leads[lead_id]
            self._persist_leads()
            conv_path = self.conversations_dir / f"{lead_id}.json"
            if conv_path.exists():
                conv_path.unlink()
            return True
        return False

    # --- Conversations ---

    def save_conversation(self, conversation: Conversation):
        path = self.conversations_dir / f"{conversation.lead_id}.json"
        path.write_text(json.dumps(conversation.to_dict(), indent=2, default=str), encoding="utf-8")

    def get_conversation(self, lead_id: str) -> Optional[Conversation]:
        path = self.conversations_dir / f"{lead_id}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return Conversation.from_dict(data)
        return None

    # --- Daily Metrics ---

    def get_today_metrics(self) -> DailyMetrics:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.metrics_dir / f"{today}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return DailyMetrics.from_dict(data)
        return DailyMetrics(date=today)

    def save_daily_metrics(self, metrics: DailyMetrics):
        path = self.metrics_dir / f"{metrics.date}.json"
        path.write_text(json.dumps(metrics.to_dict(), indent=2), encoding="utf-8")

    def increment_sent(self) -> int:
        metrics = self.get_today_metrics()
        metrics.emails_sent += 1
        self.save_daily_metrics(metrics)
        return metrics.emails_sent

    def can_send_today(self, global_limit: int = 500) -> bool:
        metrics = self.get_today_metrics()
        return metrics.emails_sent < global_limit

    # --- Pitch Deck ---

    def load_pitch_deck(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"Error: File not found: {path}"
        content = p.read_text(encoding="utf-8", errors="replace")
        dest = self.pitch_decks_dir / p.name
        dest.write_text(content, encoding="utf-8")
        return content

    def load_knowledge_base(self, root: str, limit: int = 12000) -> str:
        base = Path(root)
        if not base.exists():
            return f"Error: Knowledge directory not found: {root}"
        if not base.is_dir():
            return f"Error: Knowledge path is not a directory: {root}"

        chunks: List[str] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".txt", ".json", ".yml", ".yaml"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError as exc:
                log.warning(f"Failed reading knowledge file {path}: {exc}")
                continue
            if not text:
                continue
            rel = path.relative_to(base).as_posix()
            chunks.append(f"[FILE: {rel}]\n{text[:3000]}")
            if sum(len(c) for c in chunks) >= limit:
                break

        if not chunks:
            return "No supported knowledge files found."
        return "\n\n---\n\n".join(chunks)[:limit]

    def resolve_attachment_paths(self, attachments_dir: str, filenames: List[str]) -> List[Path]:
        if not attachments_dir or not filenames:
            return []
        root = Path(attachments_dir)
        resolved: List[Path] = []
        for name in filenames:
            candidate = (root / name).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                log.warning(f"Skipping attachment outside root: {name}")
                continue
            if candidate.exists() and candidate.is_file():
                resolved.append(candidate)
            else:
                log.warning(f"Attachment not found: {candidate}")
        return resolved

    def save_outbound_artifact(
        self,
        lead_id: str,
        subject: str,
        body: str,
        mode: str,
        attachments: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.drafts_dir / f"{lead_id}-{stamp}.json"
        payload = {
            "lead_id": lead_id,
            "subject": subject,
            "body": body,
            "mode": mode,
            "attachments": attachments or [],
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    # --- Internal ---

    def _load_campaigns(self) -> Dict[str, Campaign]:
        if self.campaigns_path.exists():
            try:
                data = json.loads(self.campaigns_path.read_text(encoding="utf-8"))
                return {c["id"]: Campaign.from_dict(c) for c in data}
            except Exception as e:
                log.warning(f"Failed to load campaigns: {e}")
        return {}

    def _persist_campaigns(self):
        data = [c.to_dict() for c in self._campaigns.values()]
        self.campaigns_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _load_leads(self) -> Dict[str, Lead]:
        if self.leads_path.exists():
            try:
                data = json.loads(self.leads_path.read_text(encoding="utf-8"))
                return {ld["id"]: Lead.from_dict(ld) for ld in data}
            except Exception as e:
                log.warning(f"Failed to load leads: {e}")
        return {}

    def _persist_leads(self):
        data = [ld.to_dict() for ld in self._leads.values()]
        self.leads_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# Module-level singleton
_store: Optional[OutreachStore] = None


def get_store() -> OutreachStore:
    global _store
    if _store is None:
        _store = OutreachStore()
    return _store
