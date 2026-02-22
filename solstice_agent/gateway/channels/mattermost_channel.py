"""
Mattermost Channel — REST API + Webhooks
=========================================
Open-source Slack alternative. Uses incoming/outgoing webhooks
and the Mattermost REST API.

No extra deps — uses httpx (already installed).
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.mattermost")


class MattermostChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._url = (config.get("url") or os.getenv("GATEWAY_MATTERMOST_URL", "")).rstrip("/")
        self._token = config.get("token") or os.getenv("GATEWAY_MATTERMOST_TOKEN", "")
        self._webhook_secret = config.get("webhook_secret") or os.getenv("GATEWAY_MATTERMOST_WEBHOOK_SECRET", "")
        self._initialized = bool(self._url and self._token)

    def validate_webhook(self, request) -> bool:
        if not self._webhook_secret:
            return True
        token = request.form.get("token") or (request.get_json(silent=True) or {}).get("token", "")
        return token == self._webhook_secret

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True) or request.form.to_dict()
            if not data:
                return None

            text = data.get("text", "").strip()
            user_id = data.get("user_id", "")
            user_name = data.get("user_name", "")
            if not text or not user_id:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.MATTERMOST,
                direction=MessageDirection.INBOUND,
                sender_id=user_id,
                sender_display_name=user_name or None,
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "channel_id": data.get("channel_id", ""),
                    "channel_name": data.get("channel_name", ""),
                    "post_id": data.get("post_id", ""),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Mattermost parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx
            channel_id = (metadata or {}).get("channel_id", recipient_id)
            resp = httpx.post(
                f"{self._url}/api/v4/posts",
                json={"channel_id": channel_id, "message": text},
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=10.0,
            )
            return {"success": resp.status_code == 201}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return {"text": response_text}
