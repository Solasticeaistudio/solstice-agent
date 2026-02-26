"""
Outreach Data Models
====================
Persistent data structures for leads, campaigns, conversations, and metrics.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional


class LeadType(str, Enum):
    INVESTOR = "investor"
    CUSTOMER = "customer"


class LeadStage(str, Enum):
    DISCOVERED = "discovered"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    REPLIED = "replied"
    ENGAGED = "engaged"
    CONVERTED = "converted"
    LOST = "lost"
    BOUNCED = "bounced"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class CampaignType(str, Enum):
    INVESTOR = "investor"
    CUSTOMER = "customer"


@dataclass
class Lead:
    id: str = ""
    lead_type: LeadType = LeadType.CUSTOMER
    stage: LeadStage = LeadStage.DISCOVERED
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    company: str = ""
    company_url: str = ""
    company_description: str = ""
    industry: str = ""
    score: int = 0
    score_reasons: List[str] = field(default_factory=list)
    research_notes: str = ""
    pain_points: List[str] = field(default_factory=list)
    campaign_id: str = ""
    source: str = ""
    source_url: str = ""
    created_at: str = ""
    updated_at: str = ""
    emails_sent: int = 0
    emails_received: int = 0
    last_contacted: str = ""
    last_reply: str = ""
    next_follow_up: str = ""
    follow_up_count: int = 0
    max_follow_ups: int = 3
    opted_out: bool = False

    def __post_init__(self):
        if not self.id:
            self.id = f"lead-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "lead_type": self.lead_type.value, "stage": self.stage.value,
            "email": self.email, "first_name": self.first_name, "last_name": self.last_name,
            "title": self.title, "company": self.company, "company_url": self.company_url,
            "company_description": self.company_description, "industry": self.industry,
            "score": self.score, "score_reasons": self.score_reasons,
            "research_notes": self.research_notes, "pain_points": self.pain_points,
            "campaign_id": self.campaign_id, "source": self.source, "source_url": self.source_url,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "emails_sent": self.emails_sent, "emails_received": self.emails_received,
            "last_contacted": self.last_contacted, "last_reply": self.last_reply,
            "next_follow_up": self.next_follow_up, "follow_up_count": self.follow_up_count,
            "max_follow_ups": self.max_follow_ups, "opted_out": self.opted_out,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        data = dict(data)
        if "lead_type" in data:
            data["lead_type"] = LeadType(data["lead_type"])
        if "stage" in data:
            data["stage"] = LeadStage(data["stage"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Campaign:
    id: str = ""
    name: str = ""
    campaign_type: CampaignType = CampaignType.CUSTOMER
    status: CampaignStatus = CampaignStatus.DRAFT
    target_criteria: str = ""
    target_industries: List[str] = field(default_factory=list)
    target_titles: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    pitch_deck_path: str = ""
    pitch_deck_content: str = ""
    value_proposition: str = ""
    email_templates: Dict[str, str] = field(default_factory=dict)
    follow_up_days: List[int] = field(default_factory=lambda: [3, 7, 14])
    send_window_start: int = 9
    send_window_end: int = 17
    daily_send_limit: int = 50
    leads_discovered: int = 0
    leads_qualified: int = 0
    emails_sent: int = 0
    replies_received: int = 0
    meetings_booked: int = 0
    opted_out: int = 0
    bounced: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"camp-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name,
            "campaign_type": self.campaign_type.value, "status": self.status.value,
            "target_criteria": self.target_criteria,
            "target_industries": self.target_industries, "target_titles": self.target_titles,
            "search_queries": self.search_queries,
            "pitch_deck_path": self.pitch_deck_path, "pitch_deck_content": self.pitch_deck_content,
            "value_proposition": self.value_proposition, "email_templates": self.email_templates,
            "follow_up_days": self.follow_up_days,
            "send_window_start": self.send_window_start, "send_window_end": self.send_window_end,
            "daily_send_limit": self.daily_send_limit,
            "leads_discovered": self.leads_discovered, "leads_qualified": self.leads_qualified,
            "emails_sent": self.emails_sent, "replies_received": self.replies_received,
            "meetings_booked": self.meetings_booked, "opted_out": self.opted_out,
            "bounced": self.bounced,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Campaign":
        data = dict(data)
        if "campaign_type" in data:
            data["campaign_type"] = CampaignType(data["campaign_type"])
        if "status" in data:
            data["status"] = CampaignStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class EmailMessage:
    id: str = ""
    direction: str = "outbound"
    subject: str = ""
    body: str = ""
    timestamp: str = ""
    message_id: str = ""
    in_reply_to: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"msg-{uuid.uuid4().hex[:8]}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "direction": self.direction, "subject": self.subject,
            "body": self.body, "timestamp": self.timestamp,
            "message_id": self.message_id, "in_reply_to": self.in_reply_to,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EmailMessage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Conversation:
    lead_id: str = ""
    campaign_id: str = ""
    messages: List[EmailMessage] = field(default_factory=list)
    status: str = "active"
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id, "campaign_id": self.campaign_id,
            "messages": [m.to_dict() for m in self.messages],
            "status": self.status, "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        data = dict(data)
        if "messages" in data:
            data["messages"] = [EmailMessage.from_dict(m) for m in data["messages"]]
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DailyMetrics:
    date: str = ""
    emails_sent: int = 0
    emails_received: int = 0
    bounces: int = 0
    opt_outs: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date, "emails_sent": self.emails_sent,
            "emails_received": self.emails_received,
            "bounces": self.bounces, "opt_outs": self.opt_outs,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DailyMetrics":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
