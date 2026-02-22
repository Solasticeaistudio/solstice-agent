"""
Nostr Channel — Decentralized social protocol
===============================================
Nostr is a censorship-resistant relay-based protocol. Messages are
sent as signed events to relays.

No extra deps — uses httpx + websockets for relay communication.
Simplified implementation using NIP-04 DMs.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.nostr")


class NostrChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._private_key = config.get("private_key") or os.getenv("GATEWAY_NOSTR_PRIVATE_KEY", "")
        self._relays = []
        relays_str = config.get("relays") or os.getenv("GATEWAY_NOSTR_RELAYS", "wss://relay.damus.io")
        if relays_str:
            self._relays = [r.strip() for r in relays_str.split(",") if r.strip()]
        self._initialized = bool(self._private_key and self._relays)

    def validate_webhook(self, request) -> bool:
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            data = request.get_json(silent=True)
            if not data:
                return None

            # Nostr event format
            kind = data.get("kind")
            if kind not in (1, 4):  # 1 = text note, 4 = DM
                return None

            content = data.get("content", "").strip()
            pubkey = data.get("pubkey", "")
            if not content or not pubkey:
                return None

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.NOSTR,
                direction=MessageDirection.INBOUND,
                sender_id=pubkey,
                text=content,
                timestamp=datetime.utcfromtimestamp(data.get("created_at", 0)),
                channel_metadata={
                    "event_id": data.get("id", ""),
                    "kind": kind,
                    "tags": data.get("tags", []),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Nostr parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            import httpx

            # Build a kind-4 DM event (simplified — full impl needs secp256k1 signing)
            event = {
                "kind": 4,
                "content": text,
                "tags": [["p", recipient_id]],
                "created_at": int(datetime.utcnow().timestamp()),
            }

            # Publish to all relays
            results = []
            for relay in self._relays:
                http_relay = relay.replace("wss://", "https://").replace("ws://", "http://")
                try:
                    resp = httpx.post(http_relay, json=["EVENT", event], timeout=5.0)
                    results.append(resp.status_code)
                except Exception:
                    results.append(0)

            success = any(r in (200, 201, 202) for r in results)
            return {"success": success, "relays_contacted": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
