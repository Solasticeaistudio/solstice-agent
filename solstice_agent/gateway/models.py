"""
Gateway Data Models
===================
Normalized message format for the messaging gateway.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum


class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    EMAIL = "email"
    TEAMS = "teams"
    GOOGLE_CHAT = "google_chat"
    SIGNAL = "signal"
    MATRIX = "matrix"
    IMESSAGE = "imessage"
    IRC = "irc"
    MATTERMOST = "mattermost"
    LINE = "line"
    TWITCH = "twitch"
    MESSENGER = "messenger"
    TWITTER = "twitter"
    REDDIT = "reddit"
    WEBHOOK = "webhook"
    NOSTR = "nostr"
    WEBCHAT = "webchat"
    FEISHU = "feishu"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class GatewayMessage:
    """Normalized message format across all channels."""
    id: str
    channel: ChannelType
    direction: MessageDirection
    sender_id: str
    text: str
    timestamp: datetime
    sender_display_name: Optional[str] = None
    recipient_id: Optional[str] = None
    channel_metadata: Dict[str, Any] = field(default_factory=dict)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"gw-{uuid.uuid4().hex[:12]}"
