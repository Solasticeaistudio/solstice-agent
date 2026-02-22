"""
WhatsApp Channel — Twilio WhatsApp API
=======================================
Uses Twilio's WhatsApp Business API. Same client as SMS, just
whatsapp:+number prefix format.

Requires: pip install twilio
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.whatsapp")


class WhatsAppChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._account_sid = config.get("account_sid") or os.getenv("TWILIO_ACCOUNT_SID", "")
        self._auth_token = config.get("auth_token") or os.getenv("TWILIO_AUTH_TOKEN", "")
        self._from_number = config.get("from_number") or os.getenv("GATEWAY_WHATSAPP_NUMBER", "")
        self._allowed = set()
        allowed_str = config.get("allowed_senders") or os.getenv("GATEWAY_WHATSAPP_ALLOWED_SENDERS", "")
        if allowed_str:
            self._allowed = {s.strip() for s in allowed_str.split(",") if s.strip()}
        self._initialized = bool(self._account_sid and self._auth_token)

    def validate_webhook(self, request) -> bool:
        # Twilio signature validation
        try:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(self._auth_token)
            url = request.url
            params = request.form.to_dict()
            signature = request.headers.get("X-Twilio-Signature", "")
            return validator.validate(url, params, signature)
        except ImportError:
            return True  # Skip validation if twilio not installed
        except Exception:
            return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        try:
            body = request.form.get("Body", "").strip()
            from_number = request.form.get("From", "")
            if not body or not from_number:
                return None

            # Strip whatsapp: prefix
            sender_id = from_number.replace("whatsapp:", "")

            if self._allowed and sender_id not in self._allowed:
                return None

            profile_name = request.form.get("ProfileName", "")

            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.WHATSAPP,
                direction=MessageDirection.INBOUND,
                sender_id=sender_id,
                sender_display_name=profile_name or None,
                text=body,
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "message_sid": request.form.get("MessageSid", ""),
                    "num_media": request.form.get("NumMedia", "0"),
                },
                raw_payload=request.form.to_dict(),
            )
        except Exception as e:
            log.error(f"WhatsApp parse error: {e}")
            return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        try:
            from twilio.rest import Client
            client = Client(self._account_sid, self._auth_token)

            if len(text) > 1600:
                text = text[:1597] + "..."

            to_number = f"whatsapp:{recipient_id}" if not recipient_id.startswith("whatsapp:") else recipient_id
            from_number = f"whatsapp:{self._from_number}" if not self._from_number.startswith("whatsapp:") else self._from_number

            msg = client.messages.create(
                body=text,
                from_=from_number,
                to=to_number,
            )
            return {"success": True, "sid": msg.sid}
        except ImportError:
            return {"success": False, "error": "twilio not installed. Run: pip install twilio"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        # TwiML response
        if len(response_text) > 1600:
            response_text = response_text[:1597] + "..."
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>{response_text}</Message></Response>'
        )
