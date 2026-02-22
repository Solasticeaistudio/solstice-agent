"""
LINE Channel — Messaging API
=============================
Popular in Japan, Thailand, Taiwan, Indonesia.
Uses LINE Messaging API with webhook + reply/push tokens.

No extra deps — uses httpx (already installed).
"""

import os
import hmac
import hashlib
import base64
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.line")


class LINEChannel(BaseChannel):

    API_BASE = "https://api.line.me/v2/bot"

    def __init__(self, config: dict):
        super().__init__(config)
        self._channel_secret = config.get("channel_secret") or os.getenv("GATEWAY_LINE_CHANNEL_SECRET", "")
        self._access_token = config.get("access_token") or os.getenv("GATEWAY_LINE_ACCESS_TOKEN", "")
        self._initialized = bool(self._access_token)

    def validate_webhook(self, request) -> bool:
        if not self._channel_secret:
            return True
        try:
            body = request.get_data()
            signature = request.headers.get("X-Line-Signature", "")
            digest = hmac.new(
                self._channel_secret.encode(), body, hashlib.sha256
            ).digest()
            return base64.b64encode(digest).decode() == signature
        except Exception:
            return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            for event in data.get("events", []):
                if event.get("type") != "message":
                    continue
                msg = event.get("message", {})
                if msg.get("type") != "text":
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    continue

                source = event.get("source", {})
                sender_id = source.get("userId", "")

                return GatewayMessage(
                    id=GatewayMessage.new_id(),
                    channel=ChannelType.LINE,
                    direction=MessageDirection.INBOUND,
                    sender_id=sender_id,
                    text=text,
                    timestamp=datetime.utcfromtimestamp(event.get("timestamp", 0) / 1000),
                    channel_metadata={
                        "reply_token": event.get("replyToken", ""),
                        "source_type": source.get("type", ""),
                        "group_id": source.get("groupId"),
                    },
                    raw_payload=event,
                )
            return None
        except Exception as e:
            log.error(f"LINE parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx
            reply_token = (metadata or {}).get("reply_token")

            headers = {"Authorization": f"Bearer {self._access_token}"}

            if reply_token:
                resp = httpx.post(
                    f"{self.API_BASE}/message/reply",
                    json={
                        "replyToken": reply_token,
                        "messages": [{"type": "text", "text": text[:5000]}],
                    },
                    headers=headers,
                    timeout=10.0,
                )
            else:
                resp = httpx.post(
                    f"{self.API_BASE}/message/push",
                    json={
                        "to": recipient_id,
                        "messages": [{"type": "text", "text": text[:5000]}],
                    },
                    headers=headers,
                    timeout=10.0,
                )
            return {"success": resp.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
