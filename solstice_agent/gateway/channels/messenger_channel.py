"""
Facebook Messenger Channel — Graph API
=======================================
Meta's Messenger Platform. Webhook for inbound, Send API for outbound.
OpenClaw doesn't have this one.

No extra deps — uses httpx (already installed).
"""

import os
import hmac
import hashlib
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.messenger")


class MessengerChannel(BaseChannel):

    GRAPH_API = "https://graph.facebook.com/v19.0"

    def __init__(self, config: dict):
        super().__init__(config)
        self._page_token = config.get("page_token") or os.getenv("GATEWAY_MESSENGER_PAGE_TOKEN", "")
        self._app_secret = config.get("app_secret") or os.getenv("GATEWAY_MESSENGER_APP_SECRET", "")
        self._verify_token = config.get("verify_token") or os.getenv("GATEWAY_MESSENGER_VERIFY_TOKEN", "")
        self._initialized = bool(self._page_token)

    def validate_webhook(self, request) -> bool:
        # GET = verification challenge
        if request.method == "GET":
            mode = request.args.get("hub.mode")
            token = request.args.get("hub.verify_token")
            return mode == "subscribe" and token == self._verify_token

        # POST = signature check
        if not self._app_secret:
            return True
        try:
            signature = request.headers.get("X-Hub-Signature-256", "")
            body = request.get_data()
            expected = "sha256=" + hmac.new(
                self._app_secret.encode(), body, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        # Handle verification challenge
        if request.method == "GET":
            return None

        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            for entry in data.get("entry", []):
                for event in entry.get("messaging", []):
                    msg = event.get("message", {})
                    text = msg.get("text", "").strip()
                    if not text:
                        continue

                    sender_id = event.get("sender", {}).get("id", "")
                    if not sender_id:
                        continue

                    return GatewayMessage(
                        id=GatewayMessage.new_id(),
                        channel=ChannelType.MESSENGER,
                        direction=MessageDirection.INBOUND,
                        sender_id=sender_id,
                        text=text,
                        timestamp=datetime.utcfromtimestamp(event.get("timestamp", 0) / 1000),
                        channel_metadata={
                            "mid": msg.get("mid", ""),
                            "recipient_id": event.get("recipient", {}).get("id", ""),
                        },
                        raw_payload=event,
                    )
            return None
        except Exception as e:
            log.error(f"Messenger parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx
            resp = httpx.post(
                f"{self.GRAPH_API}/me/messages",
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": text[:2000]},
                },
                params={"access_token": self._page_token},
                timeout=10.0,
            )
            return {"success": resp.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        # Messenger requires 200 OK, reply sent async
        return ""
