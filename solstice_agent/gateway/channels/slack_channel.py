"""
Slack Channel — Events API + WebClient
=======================================
"""

import os
import hmac
import hashlib
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.slack")


class SlackChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._bot_token = config.get("bot_token") or os.getenv("GATEWAY_SLACK_BOT_TOKEN", "")
        self._signing_secret = config.get("signing_secret") or os.getenv("GATEWAY_SLACK_SIGNING_SECRET", "")
        self._initialized = bool(self._bot_token)

    def validate_webhook(self, request) -> bool:
        if not self._signing_secret:
            return True
        try:
            timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
            signature = request.headers.get("X-Slack-Signature", "")
            if abs(time.time() - int(timestamp)) > 300:
                return False
            sig_basestring = f"v0:{timestamp}:{request.get_data(as_text=True)}"
            computed = "v0=" + hmac.new(
                self._signing_secret.encode(), sig_basestring.encode(), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(computed, signature)
        except Exception:
            return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None
            event = data.get("event", {})
            if event.get("type") != "message" or event.get("subtype") or event.get("bot_id"):
                return None

            text = event.get("text", "").strip()
            user_id = event.get("user", "")
            if not text or not user_id:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.SLACK,
                direction=MessageDirection.INBOUND,
                sender_id=user_id,
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "channel_id": event.get("channel", ""),
                    "thread_ts": event.get("thread_ts"),
                    "ts": event.get("ts"),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Slack parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            from slack_sdk import WebClient
            client = WebClient(token=self._bot_token)
            kwargs = {"channel": recipient_id, "text": text}
            if metadata and metadata.get("thread_ts"):
                kwargs["thread_ts"] = metadata["thread_ts"]
            client.chat_postMessage(**kwargs)
            return {"success": True}
        except ImportError:
            return {"success": False, "error": "slack-sdk not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
