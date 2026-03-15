"""
Email Channel — Gmail API (OAuth2) or SMTP/IMAP
================================================
Polls for new emails via IMAP, replies via SMTP or Gmail API.
Supports Gmail OAuth2 for zero-password authentication.

Requires: pip install google-auth google-auth-oauthlib google-api-python-client
(or just SMTP creds for basic mode)
"""

import os
import email
import imaplib
import smtplib
import logging
import mimetypes
from base64 import b64encode
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import Dict, Any, Optional, List
from datetime import datetime

import httpx

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.email")


class EmailChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._email = config.get("email") or os.getenv("GATEWAY_EMAIL_ADDRESS", "")
        self._password = config.get("password") or os.getenv("GATEWAY_EMAIL_PASSWORD", "")
        self._provider = (config.get("provider") or os.getenv("GATEWAY_EMAIL_PROVIDER", "smtp")).lower()
        self._imap_host = config.get("imap_host") or os.getenv("GATEWAY_EMAIL_IMAP_HOST", "imap.gmail.com")
        self._smtp_host = config.get("smtp_host") or os.getenv("GATEWAY_EMAIL_SMTP_HOST", "smtp.gmail.com")
        self._smtp_port = int(config.get("smtp_port") or os.getenv("GATEWAY_EMAIL_SMTP_PORT", "587"))
        self._graph_token = config.get("graph_token") or os.getenv("GATEWAY_EMAIL_GRAPH_TOKEN", "")
        self._graph_base = config.get("graph_base") or os.getenv("GATEWAY_EMAIL_GRAPH_BASE", "https://graph.microsoft.com/v1.0")
        self._graph_user = config.get("graph_user") or os.getenv("GATEWAY_EMAIL_GRAPH_USER", "")
        self._allowed = set()
        allowed_str = config.get("allowed_senders") or os.getenv("GATEWAY_EMAIL_ALLOWED_SENDERS", "")
        if allowed_str:
            self._allowed = {s.strip().lower() for s in allowed_str.split(",") if s.strip()}
        self._initialized = bool(self._email and (self._password or self._graph_token))

    def validate_webhook(self, request) -> bool:
        # Email doesn't use webhooks — polling-based
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        # Email uses polling, not webhooks. This is for manual feed-in.
        try:
            data = request.get_json(silent=True)
            if not data:
                return None
            return GatewayMessage(
                id=GatewayMessage.new_id(),
                channel=ChannelType.EMAIL,
                direction=MessageDirection.INBOUND,
                sender_id=data.get("from", ""),
                sender_display_name=data.get("from_name"),
                text=data.get("body", ""),
                timestamp=datetime.utcnow(),
                channel_metadata={
                    "subject": data.get("subject", ""),
                    "message_id": data.get("message_id", ""),
                },
                raw_payload=data,
            )
        except Exception as e:
            log.error(f"Email parse error: {e}")
            return None

    def poll_inbox(self, folder: str = "INBOX", unseen_only: bool = True, limit: int = 5) -> List[GatewayMessage]:
        """Poll IMAP inbox for new messages."""
        messages = []
        try:
            imap = imaplib.IMAP4_SSL(self._imap_host)
            imap.login(self._email, self._password)
            imap.select(folder)

            criteria = "UNSEEN" if unseen_only else "ALL"
            _, data = imap.search(None, criteria)
            ids = data[0].split()[-limit:] if data[0] else []

            for msg_id in ids:
                _, msg_data = imap.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                parsed = email.message_from_bytes(raw)

                sender = email.utils.parseaddr(parsed.get("From", ""))
                sender_email = sender[1].lower()
                sender_name = sender[0] or sender_email

                if self._allowed and sender_email not in self._allowed:
                    continue

                body = ""
                if parsed.is_multipart():
                    for part in parsed.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                else:
                    body = parsed.get_payload(decode=True).decode("utf-8", errors="replace")

                messages.append(GatewayMessage(
                    id=GatewayMessage.new_id(),
                    channel=ChannelType.EMAIL,
                    direction=MessageDirection.INBOUND,
                    sender_id=sender_email,
                    sender_display_name=sender_name,
                    text=body.strip(),
                    timestamp=datetime.utcnow(),
                    channel_metadata={
                        "subject": parsed.get("Subject", ""),
                        "message_id": parsed.get("Message-ID", ""),
                        "imap_id": msg_id.decode(),
                    },
                    raw_payload={},
                ))
                # Mark as seen
                imap.store(msg_id, "+FLAGS", "\\Seen")

            imap.close()
            imap.logout()
        except Exception as e:
            log.error(f"Email poll error: {e}")

        return messages

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        metadata = metadata or {}
        mode = metadata.get("mode", "send")
        if self._provider in {"outlook", "graph"}:
            if mode == "draft":
                return self.create_draft(recipient_id, text, metadata)
            return self._send_via_graph(recipient_id, text, metadata)

        try:
            subject = metadata.get("subject", "Sol Agent")
            if metadata.get("subject"):
                if not subject.startswith("Re:"):
                    subject = f"Re: {subject}"

            attachments = metadata.get("attachments") or []
            if attachments:
                msg = MIMEMultipart()
                msg.attach(MIMEText(text))
                for attachment_path in attachments:
                    self._attach_file(msg, attachment_path)
            else:
                msg = MIMEText(text)
            msg["From"] = self._email
            msg["To"] = recipient_id
            msg["Subject"] = subject

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                server.login(self._email, self._password)
                server.send_message(msg)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_draft(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        metadata = metadata or {}
        if self._provider not in {"outlook", "graph"}:
            return {
                "success": False,
                "error": "Draft creation is only supported for provider=outlook/graph.",
            }

        if not self._graph_token:
            return {"success": False, "error": "Missing GATEWAY_EMAIL_GRAPH_TOKEN."}

        payload = self._graph_message_payload(recipient_id, text, metadata)
        target = self._graph_user_target()
        url = f"{self._graph_base}/{target}/messages"
        headers = {
            "Authorization": f"Bearer {self._graph_token}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "mode": "draft",
                "draft_id": data.get("id", ""),
                "web_link": data.get("webLink", ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _send_via_graph(self, recipient_id: str, text: str, metadata: dict) -> Dict[str, Any]:
        if not self._graph_token:
            return {"success": False, "error": "Missing GATEWAY_EMAIL_GRAPH_TOKEN."}
        payload = {"message": self._graph_message_payload(recipient_id, text, metadata), "saveToSentItems": True}
        target = self._graph_user_target()
        url = f"{self._graph_base}/{target}/sendMail"
        headers = {
            "Authorization": f"Bearer {self._graph_token}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
            return {"success": True, "mode": "send"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _graph_user_target(self) -> str:
        return f"users/{self._graph_user}" if self._graph_user else "me"

    def _graph_message_payload(self, recipient_id: str, text: str, metadata: dict) -> Dict[str, Any]:
        subject = metadata.get("subject", "Sol Agent")
        payload: Dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": metadata.get("content_type", "Text"),
                "content": text,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": recipient_id,
                    }
                }
            ],
        }
        attachments = metadata.get("attachments") or []
        if attachments:
            payload["attachments"] = [self._graph_attachment(path) for path in attachments]
        return payload

    def _graph_attachment(self, attachment_path: str) -> Dict[str, Any]:
        path = os.path.abspath(attachment_path)
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type:
            mime_type = "application/octet-stream"
        with open(path, "rb") as f:
            content = b64encode(f.read()).decode("ascii")
        return {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": os.path.basename(path),
            "contentType": mime_type,
            "contentBytes": content,
        }

    def _attach_file(self, msg: MIMEMultipart, attachment_path: str):
        ctype, _ = mimetypes.guess_type(attachment_path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(attachment_path, "rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=os.path.basename(attachment_path))
        msg.attach(part)

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
