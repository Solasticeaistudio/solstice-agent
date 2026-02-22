"""
Google Chat Channel — Google Workspace Chat API
================================================
Receives events via webhook, replies via the Chat API.

Requires: pip install google-auth google-auth-httplib2 google-api-python-client
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.google_chat")


class GoogleChatChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._credentials_path = config.get("credentials_path") or os.getenv("GATEWAY_GCHAT_CREDENTIALS", "")
        self._project_id = config.get("project_id") or os.getenv("GATEWAY_GCHAT_PROJECT_ID", "")
        # Google Chat webhooks use a bearer token for verification
        self._verification_token = config.get("verification_token") or os.getenv("GATEWAY_GCHAT_VERIFICATION_TOKEN", "")
        self._initialized = bool(self._project_id)

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

            # Google Chat sends ADDED_TO_SPACE, MESSAGE, etc.
            event_type = data.get("type", "")
            if event_type != "MESSAGE":
                return None

            message = data.get("message", {})
            text = message.get("argumentText", message.get("text", "")).strip()
            if not text:
                return None

            sender = message.get("sender", {})
            sender_id = sender.get("name", "")
            display_name = sender.get("displayName", "")
            space_name = data.get("space", {}).get("name", "")

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.GOOGLE_CHAT,
                direction=MessageDirection.INBOUND,
                sender_id=sender_id,
                sender_display_name=display_name or None,
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "space_name": space_name,
                    "message_name": message.get("name", ""),
                    "thread_name": message.get("thread", {}).get("name", ""),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Google Chat parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx

            space_name = (metadata or {}).get("space_name", recipient_id)
            thread_name = (metadata or {}).get("thread_name")

            body = {"text": text}
            if thread_name:
                body["thread"] = {"name": thread_name}

            # Use service account auth
            token = self._get_access_token()
            if not token:
                return {"success": False, "error": "Failed to get Google Chat auth token"}

            url = f"https://chat.googleapis.com/v1/{space_name}/messages"
            resp = httpx.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            return {"success": resp.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_access_token(self) -> Optional[str]:
        """Get access token from service account credentials."""
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request

            creds = service_account.Credentials.from_service_account_file(
                self._credentials_path,
                scopes=["https://www.googleapis.com/auth/chat.bot"],
            )
            creds.refresh(Request())
            return creds.token
        except Exception as e:
            log.error(f"Google Chat auth error: {e}")
            return None

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        # Google Chat supports synchronous JSON reply
        return {"text": response_text}
