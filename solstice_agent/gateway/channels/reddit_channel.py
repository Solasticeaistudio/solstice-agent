"""
Reddit Channel — Reddit API (OAuth2)
=====================================
Monitor subreddits/inbox for mentions or DMs, reply via API.
OpenClaw doesn't have this one.

No extra deps — uses httpx (already installed).
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.reddit")


class RedditChannel(BaseChannel):

    API_BASE = "https://oauth.reddit.com"
    AUTH_URL = "https://www.reddit.com/api/v1/access_token"

    def __init__(self, config: dict):
        super().__init__(config)
        self._client_id = config.get("client_id") or os.getenv("GATEWAY_REDDIT_CLIENT_ID", "")
        self._client_secret = config.get("client_secret") or os.getenv("GATEWAY_REDDIT_CLIENT_SECRET", "")
        self._username = config.get("username") or os.getenv("GATEWAY_REDDIT_USERNAME", "")
        self._password = config.get("password") or os.getenv("GATEWAY_REDDIT_PASSWORD", "")
        self._access_token = None
        self._initialized = bool(self._client_id and self._client_secret and self._username)

    def _get_token(self) -> Optional[str]:
        if self._access_token:
            return self._access_token
        try:
            import httpx
            resp = httpx.post(
                self.AUTH_URL,
                data={"grant_type": "password", "username": self._username, "password": self._password},
                auth=(self._client_id, self._client_secret),
                headers={"User-Agent": "Sol/0.1"},
                timeout=10.0,
            )
            self._access_token = resp.json().get("access_token")
            return self._access_token
        except Exception:
            return None

    def validate_webhook(self, request) -> bool:
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            text = data.get("body", data.get("selftext", "")).strip()
            author = data.get("author", "")
            if not text or not author:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.REDDIT,
                direction=MessageDirection.INBOUND,
                sender_id=author,
                sender_display_name=author,
                text=text,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "subreddit": data.get("subreddit", ""),
                    "thing_id": data.get("name", ""),
                    "parent_id": data.get("parent_id", ""),
                    "link_id": data.get("link_id", ""),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Reddit parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx
            token = self._get_token()
            if not token:
                return {"success": False, "error": "Reddit auth failed"}

            thing_id = (metadata or {}).get("thing_id", recipient_id)
            headers = {"Authorization": f"Bearer {token}", "User-Agent": "Sol/0.1"}

            resp = httpx.post(
                f"{self.API_BASE}/api/comment",
                data={"thing_id": thing_id, "text": text},
                headers=headers,
                timeout=10.0,
            )
            return {"success": resp.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
