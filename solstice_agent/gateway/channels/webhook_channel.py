"""
Generic Webhook Channel — Universal catch-all
==============================================
Accepts any JSON payload via webhook. The most flexible channel —
works with anything that can send/receive HTTP.

Pairs with Blackbox: if the platform has an API, Sol can talk to it.

No extra deps.
"""

import os
import hmac
import hashlib
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.webhook")


class WebhookChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._secret = config.get("secret") or os.getenv("GATEWAY_WEBHOOK_SECRET", "")
        self._callback_url = config.get("callback_url") or os.getenv("GATEWAY_WEBHOOK_CALLBACK_URL", "")
        self._text_field = config.get("text_field", "text")
        self._sender_field = config.get("sender_field", "sender")
        self._initialized = True  # Always available

    def validate_webhook(self, request) -> bool:
        if not self._secret:
            return True
        try:
            signature = request.headers.get("X-Webhook-Signature", "")
            body = request.get_data()
            expected = hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            # Flexible field extraction
            text = self._extract(data, self._text_field)
            sender = self._extract(data, self._sender_field) or "webhook"
            if not text:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.WEBHOOK,
                direction=MessageDirection.INBOUND,
                sender_id=str(sender),
                text=str(text),
                timestamp=datetime.utcnow(),
                channel_metadata={"source": request.headers.get("User-Agent", "unknown")},
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Webhook parse error: {e}")
            return None

    def _extract(self, data: dict, field_path: str) -> Optional[str]:
        """Extract a value from nested dict using dot notation (e.g. 'message.text')."""
        parts = field_path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return str(current) if current is not None else None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        if not self._callback_url:
            return {"success": False, "error": "No callback URL configured"}
        try:
            import httpx
            payload = {"text": text, "recipient": recipient_id}
            if metadata:
                payload["metadata"] = metadata
            resp = httpx.post(self._callback_url, json=payload, timeout=10.0)
            return {"success": resp.status_code in (200, 201, 202)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return {"response": response_text}
