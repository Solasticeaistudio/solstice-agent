"""
Twitch Channel — IRC-based chat
================================
Twitch chat uses IRC under the hood. Connects to Twitch IRC,
listens in configured channels, responds to messages.

No extra deps — raw socket connection.
"""

import os
import socket
import ssl
import threading
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.twitch")


class TwitchChannel(BaseChannel):

    IRC_HOST = "irc.chat.twitch.tv"
    IRC_PORT = 6697

    def __init__(self, config: dict):
        super().__init__(config)
        self._oauth_token = config.get("oauth_token") or os.getenv("GATEWAY_TWITCH_OAUTH_TOKEN", "")
        self._nick = (config.get("nick") or os.getenv("GATEWAY_TWITCH_NICK", "")).lower()
        self._channels_list = []
        channels_str = config.get("channels") or os.getenv("GATEWAY_TWITCH_CHANNELS", "")
        if channels_str:
            self._channels_list = [c.strip().lower().lstrip("#") for c in channels_str.split(",") if c.strip()]
        self._sock = None
        self._on_message = None
        self._initialized = bool(self._oauth_token and self._nick and self._channels_list)

    def start_bot(self, on_message_callback: Callable):
        if not self._initialized:
            return
        self._on_message = on_message_callback

        def _run():
            try:
                raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ctx = ssl.create_default_context()
                self._sock = ctx.wrap_socket(raw, server_hostname=self.IRC_HOST)
                self._sock.connect((self.IRC_HOST, self.IRC_PORT))

                token = self._oauth_token if self._oauth_token.startswith("oauth:") else f"oauth:{self._oauth_token}"
                self._send(f"PASS {token}")
                self._send(f"NICK {self._nick}")

                for ch in self._channels_list:
                    self._send(f"JOIN #{ch}")

                buf = ""
                while True:
                    data = self._sock.recv(4096).decode("utf-8", errors="replace")
                    if not data:
                        break
                    buf += data
                    while "\r\n" in buf:
                        line, buf = buf.split("\r\n", 1)
                        self._handle_line(line)
            except Exception as e:
                log.error(f"Twitch IRC error: {e}")

        thread = threading.Thread(target=_run, daemon=True, name="twitch-bot")
        thread.start()
        log.info(f"Twitch bot connecting to {self.IRC_HOST}")

    def _send(self, msg: str):
        if self._sock:
            self._sock.send(f"{msg}\r\n".encode("utf-8"))

    def _handle_line(self, line: str):
        if line.startswith("PING"):
            self._send(line.replace("PING", "PONG", 1))
            return

        if "PRIVMSG" in line:
            try:
                prefix, rest = line[1:].split(" ", 1)
                nick = prefix.split("!")[0]
                if nick.lower() == self._nick:
                    return
                parts = rest.split(" ", 2)
                target = parts[1]
                text = parts[2][1:] if parts[2].startswith(":") else parts[2]

                msg = GatewayMessage(
                    id=GatewayMessage.new_id(),
                    channel=ChannelType.TWITCH,
                    direction=MessageDirection.INBOUND,
                    sender_id=nick,
                    sender_display_name=nick,
                    text=text.strip(),
                    timestamp=datetime.utcnow(),
                    channel_metadata={"target": target},
                )
                response = self._on_message(msg) if self._on_message else None
                if response:
                    for chunk in [response[i:i+450] for i in range(0, len(response), 450)][:3]:
                        self._send(f"PRIVMSG {target} :{chunk}")
            except Exception as e:
                log.debug(f"Twitch parse error: {e}")

    def validate_webhook(self, request) -> bool:
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        return None

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        if not self._sock:
            return {"success": False, "error": "Twitch not connected"}
        try:
            target = (metadata or {}).get("target", f"#{recipient_id}")
            for chunk in [text[i:i+450] for i in range(0, len(text), 450)][:3]:
                self._send(f"PRIVMSG {target} :{chunk}")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
