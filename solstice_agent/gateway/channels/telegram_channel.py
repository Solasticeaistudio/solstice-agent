"""
Telegram Channel — Raw httpx to Telegram Bot API
=================================================
No heavy library — just HTTP calls to api.telegram.org.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.telegram")


class TelegramChannel(BaseChannel):

    API_BASE = "https://api.telegram.org/bot{token}"

    def __init__(self, config: dict):
        super().__init__(config)
        self._token = config.get("bot_token") or os.getenv("GATEWAY_TELEGRAM_BOT_TOKEN", "")
        self._webhook_secret = config.get("webhook_secret") or os.getenv("GATEWAY_TELEGRAM_WEBHOOK_SECRET", "")
        self._allowed = set()
        allowed_str = config.get("allowed_senders") or os.getenv("GATEWAY_TELEGRAM_ALLOWED_SENDERS", "")
        if allowed_str:
            self._allowed = {s.strip() for s in allowed_str.split(",") if s.strip()}
        self._initialized = bool(self._token)

    def _api_url(self, method: str) -> str:
        return f"{self.API_BASE.format(token=self._token)}/{method}"

    def validate_webhook(self, request) -> bool:
        if not self._webhook_secret:
            return True
        return request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") == self._webhook_secret

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            message = data.get("message") or data.get("edited_message")
            if not message:
                return None

            text = message.get("text", "").strip()
            if not text:
                return None

            sender = message.get("from", {})
            sender_id = str(sender.get("id", ""))
            chat_id = str(message.get("chat", {}).get("id", ""))

            if self._allowed and sender_id not in self._allowed:
                return None

            display_name = sender.get("first_name", "")
            if sender.get("last_name"):
                display_name += f" {sender['last_name']}"

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.TELEGRAM,
                direction=MessageDirection.INBOUND,
                sender_id=sender_id,
                sender_display_name=display_name or None,
                text=text,
                timestamp=datetime.utcfromtimestamp(message.get("date", 0)),
                channel_metadata={"chat_id": chat_id, "message_id": message.get("message_id")},
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Telegram parse error: {e}", exc_info=True)
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx

            if len(text) > 4000:
                text = text[:3997] + "..."

            chat_id = recipient_id
            if metadata and metadata.get("chat_id"):
                chat_id = metadata["chat_id"]

            resp = httpx.post(
                self._api_url("sendMessage"),
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10.0,
            )

            if resp.status_code == 200:
                return {"success": True}
            elif "can't parse" in resp.text.lower():
                resp = httpx.post(
                    self._api_url("sendMessage"),
                    json={"chat_id": chat_id, "text": text},
                    timeout=10.0,
                )
                return {"success": resp.status_code == 200}
            return {"success": False, "error": resp.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
