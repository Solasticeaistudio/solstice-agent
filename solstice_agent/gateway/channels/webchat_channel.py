"""
WebChat Channel — Embeddable web widget
========================================
A simple HTTP-based chat endpoint. Embed in any website with a
JavaScript snippet. POST messages, get responses.

No extra deps.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.webchat")


class WebChatChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._api_key = config.get("api_key") or os.getenv("GATEWAY_WEBCHAT_API_KEY", "")
        self._allowed_origins = set()
        origins_str = config.get("allowed_origins") or os.getenv("GATEWAY_WEBCHAT_ALLOWED_ORIGINS", "")
        if origins_str:
            self._allowed_origins = {s.strip() for s in origins_str.split(",") if s.strip()}
        self._initialized = True  # Always available

    def validate_webhook(self, request) -> bool:
        if self._api_key:
            auth = request.headers.get("Authorization", "").replace("Bearer ", "")
            if auth != self._api_key:
                return False
        if self._allowed_origins:
            origin = request.headers.get("Origin", "")
            if origin and origin not in self._allowed_origins:
                return False
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            text = data.get("message", data.get("text", "")).strip()
            session_id = data.get("session_id", data.get("user_id", "anonymous"))
            if not text:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.WEBCHAT,
                direction=MessageDirection.INBOUND,
                sender_id=str(session_id),
                sender_display_name=data.get("name"),
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "session_id": str(session_id),
                    "page_url": data.get("page_url", ""),
                    "user_agent": request.headers.get("User-Agent", ""),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"WebChat parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        # WebChat is synchronous — response is returned in format_webhook_response
        return {"success": True, "text": text}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return {
            "response": response_text,
            "session_id": inbound_msg.sender_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
