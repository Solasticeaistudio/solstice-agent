"""
Discord Channel — discord.py bot in background thread
=====================================================
Persistent WebSocket bot. Listens for messages, responds via the bot client.
"""

import os
import asyncio
import threading
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from ..base_channel import BaseChannel
from ..models import GatewayMessage, ChannelType, MessageDirection

log = logging.getLogger("solstice.gateway.discord")


class DiscordChannel(BaseChannel):

    def __init__(self, config: dict):
        super().__init__(config)
        self._token = config.get("bot_token") or os.getenv("GATEWAY_DISCORD_BOT_TOKEN", "")
        self._channel_ids = set()
        channels_str = config.get("channel_ids") or os.getenv("GATEWAY_DISCORD_CHANNEL_IDS", "")
        if channels_str:
            self._channel_ids = {s.strip() for s in channels_str.split(",") if s.strip()}
        self._allowed_users = set()
        users_str = config.get("allowed_users") or os.getenv("GATEWAY_DISCORD_ALLOWED_USERS", "")
        if users_str:
            self._allowed_users = {s.strip() for s in users_str.split(",") if s.strip()}
        self._bot_client = None
        self._loop = None
        self._initialized = bool(self._token)

    def start_bot(self, on_message_callback: Callable):
        """Start the Discord bot in a background daemon thread."""
        if not self._initialized:
            return

        def _run():
            try:
                import discord

                intents = discord.Intents.default()
                intents.message_content = True
                client = discord.Client(intents=intents)
                self._bot_client = client

                @client.event
                async def on_ready():
                    log.info(f"Discord bot connected as {client.user}")

                @client.event
                async def on_message(message):
                    if message.author.bot:
                        return
                    if self._channel_ids and str(message.channel.id) not in self._channel_ids:
                        return
                    if self._allowed_users and str(message.author.id) not in self._allowed_users:
                        return

                    text = message.content.strip()
                    if not text:
                        return

                    msg = GatewayMessage(
                        id=GatewayMessage.new_id(),
                        channel=ChannelType.DISCORD,
                        direction=MessageDirection.INBOUND,
                        sender_id=str(message.author.id),
                        sender_display_name=str(message.author),
                        text=text,
                        timestamp=datetime.utcnow(),
                        channel_metadata={"channel_id": str(message.channel.id)},
                    )

                    response_text = on_message_callback(msg)
                    if response_text:
                        if len(response_text) > 1900:
                            response_text = response_text[:1900] + "..."
                        await message.channel.send(response_text)

                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_until_complete(client.start(self._token))
            except ImportError:
                log.error("discord.py not installed. Run: pip install discord.py")
            except Exception as e:
                log.error(f"Discord bot error: {e}")

        thread = threading.Thread(target=_run, daemon=True, name="discord-bot")
        thread.start()
        log.info("Discord bot thread started")

    def validate_webhook(self, request) -> bool:
        return True

    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        return None  # Inbound handled by bot thread

    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        if not self._bot_client or not self._loop:
            return {"success": False, "error": "Discord bot not running"}

        try:
            channel = self._bot_client.get_channel(int(recipient_id))
            if not channel:
                return {"success": False, "error": f"Channel {recipient_id} not found"}

            if len(text) > 1900:
                text = text[:1900] + "..."

            future = asyncio.run_coroutine_threadsafe(channel.send(text), self._loop)
            future.result(timeout=10)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        return ""
