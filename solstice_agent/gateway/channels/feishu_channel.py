"""
Feishu/Lark Channel — ByteDance Messaging Platform
===================================================
Popular in China and Asia-Pacific. Feishu (飞书) is the Chinese version,
Lark is the international version. Same API.

No extra deps — uses httpx (already installed).
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.feishu")


class FeishuChannel(BaseChannel):

    API_BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, config: dict):
        super().__init__(config)
        self._app_id = config.get("app_id") or os.getenv("GATEWAY_FEISHU_APP_ID", "")
        self._app_secret = config.get("app_secret") or os.getenv("GATEWAY_FEISHU_APP_SECRET", "")
        self._verification_token = config.get("verification_token") or os.getenv("GATEWAY_FEISHU_VERIFICATION_TOKEN", "")
        self._encrypt_key = config.get("encrypt_key") or os.getenv("GATEWAY_FEISHU_ENCRYPT_KEY", "")
        self._initialized = bool(self._app_id and self._app_secret)

    def validate_webhook(self, request) -> bool:
        if not self._verification_token:
            return True
        data = request.get_json(silent=True) or {}
        return data.get("token", "") == self._verification_token

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            # URL verification challenge
            if data.get("type") == "url_verification":
                return None

            header = data.get("header", {})
            event = data.get("event", {})

            if header.get("event_type") != "im.message.receive_v1":
                return None

            message = event.get("message", {})
            msg_type = message.get("message_type", "")
            if msg_type != "text":
                return None

            content = message.get("content", "{}")
            import json as _json
            text = _json.loads(content).get("text", "").strip()
            if not text:
                return None

            sender = event.get("sender", {}).get("sender_id", {})
            sender_id = sender.get("open_id", "")
            chat_id = message.get("chat_id", "")

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.FEISHU,
                direction=MessageDirection.INBOUND,
                sender_id=sender_id,
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "chat_id": chat_id,
                    "message_id": message.get("message_id", ""),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Feishu parse error: {e}")
            return None

    def _get_tenant_token(self) -> Optional[str]:
        try:
            import httpx
            resp = httpx.post(
                f"{self.API_BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
                timeout=10.0,
            )
            return resp.json().get("tenant_access_token")
        except Exception:
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx
            token = self._get_tenant_token()
            if not token:
                return {"success": False, "error": "Feishu auth failed"}

            chat_id = (metadata or {}).get("chat_id", recipient_id)
            resp = httpx.post(
                f"{self.API_BASE}/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                json={
                    "receive_id": chat_id,
                    "msg_type": "text",
                    "content": f'{{"text": "{text}"}}',
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            return {"success": resp.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
