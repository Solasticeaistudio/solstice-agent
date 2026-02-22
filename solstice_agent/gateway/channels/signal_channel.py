"""
Signal Channel — signal-cli REST API
=====================================
Uses signal-cli-rest-api as a bridge. Self-hosted, E2E encrypted.
Deploy signal-cli-rest-api via Docker, then point this channel at it.

See: https://github.com/bbernhard/signal-cli-rest-api
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.signal")


class SignalChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._api_url = (
            config.get("api_url") or os.getenv("GATEWAY_SIGNAL_API_URL", "http://localhost:8080")
        ).rstrip("/")
        self._phone_number = config.get("phone_number") or os.getenv("GATEWAY_SIGNAL_NUMBER", "")
        self._allowed = set()
        allowed_str = config.get("allowed_senders") or os.getenv("GATEWAY_SIGNAL_ALLOWED_SENDERS", "")
        if allowed_str:
            self._allowed = {s.strip() for s in allowed_str.split(",") if s.strip()}
        self._initialized = bool(self._phone_number)

    def validate_webhook(self, request) -> bool:
        # signal-cli-rest-api doesn't do signature validation
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            envelope = data.get("envelope", {})
            data_msg = envelope.get("dataMessage")
            if not data_msg:
                return None

            text = data_msg.get("message", "").strip()
            if not text:
                return None

            source = envelope.get("source", "")
            source_name = envelope.get("sourceName", "")

            if self._allowed and source not in self._allowed:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.SIGNAL,
                direction=MessageDirection.INBOUND,
                sender_id=source,
                sender_display_name=source_name or None,
                text=text,
                timestamp=datetime.utcfromtimestamp(envelope.get("timestamp", 0) / 1000),
                channel_metadata={
                    "timestamp": envelope.get("timestamp"),
                    "group_id": data_msg.get("groupInfo", {}).get("groupId"),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Signal parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx

            group_id = (metadata or {}).get("group_id")

            if group_id:
                payload = {
                    "message": text,
                    "number": self._phone_number,
                    "recipients": [group_id],
                }
                endpoint = f"{self._api_url}/v2/send"
            else:
                payload = {
                    "message": text,
                    "number": self._phone_number,
                    "recipients": [recipient_id],
                }
                endpoint = f"{self._api_url}/v2/send"

            resp = httpx.post(endpoint, json=payload, timeout=10.0)
            return {"success": resp.status_code in (200, 201)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
