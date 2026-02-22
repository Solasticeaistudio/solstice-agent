"""
iMessage Channel — via BlueBubbles or pypush
=============================================
iMessage doesn't have a public API. This channel works through
BlueBubbles (self-hosted macOS server) or compatible bridges.

See: https://bluebubbles.app

Requires a Mac running BlueBubbles server. No extra Python deps
beyond httpx (already installed).
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.imessage")


class IMessageChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._api_url = (
            config.get("api_url") or os.getenv("GATEWAY_IMESSAGE_API_URL", "http://localhost:1234")
        ).rstrip("/")
        self._password = config.get("password") or os.getenv("GATEWAY_IMESSAGE_PASSWORD", "")
        self._allowed = set()
        allowed_str = config.get("allowed_senders") or os.getenv("GATEWAY_IMESSAGE_ALLOWED_SENDERS", "")
        if allowed_str:
            self._allowed = {s.strip().lower() for s in allowed_str.split(",") if s.strip()}
        self._initialized = bool(self._api_url and self._password)

    def validate_webhook(self, request) -> bool:
        # BlueBubbles can be configured with a webhook password
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            # BlueBubbles webhook payload
            event_type = data.get("type", "")
            if event_type != "new-message":
                return None

            message = data.get("data", {})
            text = message.get("text", "").strip()
            if not text:
                return None

            # Handle info from the message
            handle = message.get("handle", {})
            sender_id = handle.get("address", "")
            if not sender_id:
                return None

            if self._allowed and sender_id.lower() not in self._allowed:
                return None

            is_from_me = message.get("isFromMe", False)
            if is_from_me:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.IMESSAGE,
                direction=MessageDirection.INBOUND,
                sender_id=sender_id,
                sender_display_name=handle.get("firstName") or sender_id,
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "chat_guid": message.get("chats", [{}])[0].get("guid", "") if message.get("chats") else "",
                    "message_guid": message.get("guid", ""),
                    "is_imessage": message.get("isIMessage", True),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"iMessage parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx

            chat_guid = (metadata or {}).get("chat_guid", "")

            if chat_guid:
                # Reply to existing chat
                resp = httpx.post(
                    f"{self._api_url}/api/v1/message/text",
                    json={
                        "chatGuid": chat_guid,
                        "message": text,
                    },
                    params={"password": self._password},
                    timeout=10.0,
                )
            else:
                # New message by address
                resp = httpx.post(
                    f"{self._api_url}/api/v1/message/text",
                    json={
                        "chatGuid": f"iMessage;-;{recipient_id}",
                        "message": text,
                    },
                    params={"password": self._password},
                    timeout=10.0,
                )

            return {"success": resp.status_code in (200, 201)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
