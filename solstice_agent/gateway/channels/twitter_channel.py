"""
Twitter/X Channel — DM via API v2
==================================
Direct messages on X (formerly Twitter). Uses the v2 API.
OpenClaw doesn't have this one either.

No extra deps — uses httpx (already installed).
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.twitter")


class TwitterChannel(BaseChannel):

    API_BASE = "https://api.x.com/2"

    def __init__(self, config: dict):
        super().__init__(config)
        self._bearer_token = config.get("bearer_token") or os.getenv("GATEWAY_TWITTER_BEARER_TOKEN", "")
        self._access_token = config.get("access_token") or os.getenv("GATEWAY_TWITTER_ACCESS_TOKEN", "")
        self._access_secret = config.get("access_secret") or os.getenv("GATEWAY_TWITTER_ACCESS_SECRET", "")
        self._bot_user_id = config.get("bot_user_id") or os.getenv("GATEWAY_TWITTER_BOT_USER_ID", "")
        self._initialized = bool(self._bearer_token and self._bot_user_id)

    def validate_webhook(self, request) -> bool:
        # Twitter Account Activity API uses CRC validation
        if request.method == "GET":
            # CRC challenge — would need to compute HMAC response
            return True
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            # Account Activity API DM event
            dm_events = data.get("direct_message_events", [])
            for event in dm_events:
                if event.get("type") != "message_create":
                    continue

                msg_data = event.get("message_create", {})
                sender_id = msg_data.get("sender_id", "")

                # Skip own messages
                if sender_id == self._bot_user_id:
                    continue

                text = msg_data.get("message_data", {}).get("text", "").strip()
                if not text:
                    continue

                return GatewayMessage(
                    id=GatewayMessage.new_id(),
                    channel=ChannelType.TWITTER,
                    direction=MessageDirection.INBOUND,
                    sender_id=sender_id,
                    text=text,
                    timestamp=datetime.utcnow(),
                    channel_metadata={
                        "dm_event_id": event.get("id", ""),
                        "recipient_id": msg_data.get("target", {}).get("recipient_id", ""),
                    },
                    raw_payload=event,
                )
            return None
        except Exception as e:
            log.error(f"Twitter parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx
            resp = httpx.post(
                f"{self.API_BASE}/dm_conversations/with/{recipient_id}/messages",
                json={"text": text[:10000]},
                headers={"Authorization": f"Bearer {self._bearer_token}"},
                timeout=10.0,
            )
            return {"success": resp.status_code in (200, 201)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
