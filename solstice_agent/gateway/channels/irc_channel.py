"""
IRC Channel — Raw socket IRC client
====================================
Classic IRC. Connects to any IRC server, joins channels, responds to messages.
No external deps — uses Python's built-in socket and ssl modules.
"""

import os
import ssl
import socket
import threading
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.irc")


class IRCChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._server = config.get("server") or os.getenv("GATEWAY_IRC_SERVER", "irc.libera.chat")
        self._port = int(config.get("port") or os.getenv("GATEWAY_IRC_PORT", "6697"))
        self._nick = config.get("nick") or os.getenv("GATEWAY_IRC_NICK", "SolBot")
        self._channels_list = []
        channels_str = config.get("channels") or os.getenv("GATEWAY_IRC_CHANNELS", "")
        if channels_str:
            self._channels_list = [c.strip() for c in channels_str.split(",") if c.strip()]
        self._use_ssl = config.get("use_ssl", True)
        self._sock = None
        self._on_message = None
        self._initialized = bool(self._channels_list)

    def start_bot(self, on_message_callback: Callable):
        """Start IRC client in a background thread."""
        if not self._initialized:
            return
        self._on_message = on_message_callback

        def _run():
            try:
                raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if self._use_ssl:
                    ctx = ssl.create_default_context()
                    self._sock = ctx.wrap_socket(raw, server_hostname=self._server)
                else:
                    self._sock = raw

                self._sock.connect((self._server, self._port))
                self._send(f"NICK {self._nick}")
                self._send(f"USER {self._nick} 0 * :Sol Agent")

                for ch in self._channels_list:
                    self._send(f"JOIN {ch}")

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
                log.error(f"IRC error: {e}")

        thread = threading.Thread(target=_run, daemon=True, name="irc-bot")
        thread.start()
        log.info(f"IRC bot connecting to {self._server}:{self._port}")

    def _send(self, msg: str):
        if self._sock:
            self._sock.send(f"{msg}\r\n".encode("utf-8"))

    def _handle_line(self, line: str):
        if line.startswith("PING"):
            self._send(line.replace("PING", "PONG", 1))
            return

        # :nick!user@host PRIVMSG #channel :message text
        if "PRIVMSG" in line:
            try:
                prefix, rest = line[1:].split(" ", 1)
                nick = prefix.split("!")[0]
                parts = rest.split(" ", 2)
                target = parts[1]
                text = parts[2][1:] if parts[2].startswith(":") else parts[2]

                msg = GatewayMessage(
                    id=GatewayMessage.new_id(),
                    channel=ChannelType.IRC,
                    direction=MessageDirection.INBOUND,
                    sender_id=nick,
                    sender_display_name=nick,
                    text=text.strip(),
                    timestamp=datetime.utcnow(),
                    channel_metadata={"target": target},
                )
                response = self._on_message(msg) if self._on_message else None
                if response:
                    for line_out in response.split("\n")[:5]:
                        self._send(f"PRIVMSG {target} :{line_out}")
            except Exception as e:
                log.debug(f"IRC parse error: {e}")

    def validate_webhook(self, request) -> bool:
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        return None  # Handled by bot thread

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        if not self._sock:
            return {"success": False, "error": "IRC not connected"}
        try:
            target = (metadata or {}).get("target", recipient_id)
            for line in text.split("\n")[:10]:
                self._send(f"PRIVMSG {target} :{line}")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
