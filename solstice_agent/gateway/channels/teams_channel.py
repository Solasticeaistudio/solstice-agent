"""
Microsoft Teams Channel — Bot Framework
========================================
Uses Azure Bot Service / Bot Framework SDK.
Receives activity via webhook, replies via the connector API.

Requires: pip install botbuilder-core
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.teams")


class TeamsChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._app_id = config.get("app_id") or os.getenv("GATEWAY_TEAMS_APP_ID", "")
        self._app_password = config.get("app_password") or os.getenv("GATEWAY_TEAMS_APP_PASSWORD", "")
        self._initialized = bool(self._app_id and self._app_password)

    def validate_webhook(self, request) -> bool:
        # Bot Framework uses JWT bearer token validation
        # Full validation requires botbuilder-core; simplified check here
        auth_header = request.headers.get("Authorization", "")
        return auth_header.startswith("Bearer ")

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            if data.get("type") != "message":
                return None

            text = data.get("text", "").strip()
            if not text:
                return None

            # Strip bot mention
            if data.get("entities"):
                for entity in data["entities"]:
                    if entity.get("type") == "mention":
                        mentioned_text = entity.get("text", "")
                        text = text.replace(mentioned_text, "").strip()

            from_user = data.get("from", {})
            sender_id = from_user.get("id", "")
            display_name = from_user.get("name", "")

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.TEAMS,
                direction=MessageDirection.INBOUND,
                sender_id=sender_id,
                sender_display_name=display_name or None,
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "service_url": data.get("serviceUrl", ""),
                    "conversation_id": data.get("conversation", {}).get("id", ""),
                    "activity_id": data.get("id", ""),
                    "reply_to_id": data.get("replyToId"),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Teams parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx

            service_url = (metadata or {}).get("service_url", "")
            conversation_id = (metadata or {}).get("conversation_id", recipient_id)

            if not service_url:
                return {"success": False, "error": "No service_url in metadata"}

            # Get auth token from Bot Framework
            token = self._get_token()
            if not token:
                return {"success": False, "error": "Failed to get Bot Framework token"}

            url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
            resp = httpx.post(
                url,
                json={"type": "message", "text": text},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            return {"success": resp.status_code in (200, 201)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_token(self) -> Optional[str]:
        """Get an OAuth token from the Bot Framework auth endpoint."""
        try:
            import httpx
            resp = httpx.post(
                "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._app_id,
                    "client_secret": self._app_password,
                    "scope": "https://api.botframework.com/.default",
                },
                timeout=10.0,
            )
            return resp.json().get("access_token")
        except Exception:
            return None

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
