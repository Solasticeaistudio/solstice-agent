"""
Matrix Channel — Matrix Client-Server API
==========================================
Open, federated, E2E encrypted messaging. Uses the Matrix client-server API.
Compatible with Element, FluffyChat, and all Matrix clients.

No extra deps — uses httpx (already installed).
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.matrix")


class MatrixChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._homeserver = (
            config.get("homeserver") or os.getenv("GATEWAY_MATRIX_HOMESERVER", "https://matrix.org")
        ).rstrip("/")
        self._access_token = config.get("access_token") or os.getenv("GATEWAY_MATRIX_ACCESS_TOKEN", "")
        self._user_id = config.get("user_id") or os.getenv("GATEWAY_MATRIX_USER_ID", "")
        self._room_ids = set()
        rooms_str = config.get("room_ids") or os.getenv("GATEWAY_MATRIX_ROOM_IDS", "")
        if rooms_str:
            self._room_ids = {s.strip() for s in rooms_str.split(",") if s.strip()}
        self._initialized = bool(self._access_token and self._user_id)

    def validate_webhook(self, request) -> bool:
        # Matrix uses Application Service API with hs_token
        hs_token = request.args.get("access_token", "")
        expected = os.getenv("GATEWAY_MATRIX_HS_TOKEN", "")
        if not expected:
            return True
        return hs_token == expected

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            events = data.get("events", [data]) if "events" not in data else data["events"]

            for event in events:
                if event.get("type") != "m.room.message":
                    continue

                content = event.get("content", {})
                if content.get("msgtype") != "m.text":
                    continue

                text = content.get("body", "").strip()
                sender = event.get("sender", "")
                room_id = event.get("room_id", "")

                # Skip own messages
                if sender == self._user_id:
                    continue

                if self._room_ids and room_id not in self._room_ids:
                    continue

                if not text:
                    continue

                return GatewayMessage(
                    id=GatewayMessage.new_id(),
                    channel=ChannelType.MATRIX,
                    direction=MessageDirection.INBOUND,
                    sender_id=sender,
                    text=text,
                    timestamp=datetime.utcfromtimestamp(event.get("origin_server_ts", 0) / 1000),
                    channel_metadata={
                        "room_id": room_id,
                        "event_id": event.get("event_id", ""),
                    },
                    raw_payload=event,
                )

            return None
        except Exception as e:
            log.error(f"Matrix parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx
            import uuid

            room_id = (metadata or {}).get("room_id", recipient_id)
            txn_id = uuid.uuid4().hex[:12]

            url = (
                f"{self._homeserver}/_matrix/client/v3/rooms/{room_id}"
                f"/send/m.room.message/{txn_id}"
            )
            resp = httpx.put(
                url,
                json={"msgtype": "m.text", "body": text},
                headers={"Authorization": f"Bearer {self._access_token}"},
                timeout=10.0,
            )
            return {"success": resp.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return {}
