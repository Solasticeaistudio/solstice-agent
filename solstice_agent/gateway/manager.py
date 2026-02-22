"""
Gateway Manager — Standalone
=============================
Routes inbound messages to the framework's Agent (not Solstice services).
Manages per-sender conversation history and proactive outbound.
"""

import os
import logging
from typing import Dict, List, Any, Optional

from .models import ChannelType, GatewayMessage
from .base_channel import BaseChannel

log = logging.getLogger("solstice.gateway.manager")


class GatewayManager:
    """
    Central orchestrator for the messaging gateway.
    Routes messages to your Agent instance.
    """

    MAX_HISTORY = 20

    def __init__(self, agent=None, pool=None, router=None):
        """
        Args:
            agent: An Agent instance to handle messages (single-agent mode).
            pool: An AgentPool for multi-agent routing.
            router: An AgentRouter for multi-agent routing.
        """
        self.agent = agent
        self._pool = pool
        self._router = router
        self.channels: Dict[ChannelType, BaseChannel] = {}
        self._conversations: Dict[str, List[Dict]] = {}

    def set_agent(self, agent):
        """Set the agent that handles messages."""
        self.agent = agent

    def register_channel(self, channel_type: ChannelType, channel: BaseChannel):
        """Register a channel adapter."""
        self.channels[channel_type] = channel
        log.info(f"Registered channel: {channel_type.value}")

    def auto_configure(self, config: dict = None):
        """Auto-register channels based on config dict or environment variables."""
        config = config or {}

        # Telegram
        tg_config = config.get("telegram", {})
        if tg_config.get("enabled") or os.getenv("GATEWAY_TELEGRAM_ENABLED", "").lower() == "true":
            try:
                from .channels.telegram_channel import TelegramChannel
                ch = TelegramChannel(tg_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.TELEGRAM, ch)
            except Exception as e:
                log.error(f"Failed to configure Telegram: {e}")

        # Discord
        dc_config = config.get("discord", {})
        if dc_config.get("enabled") or os.getenv("GATEWAY_DISCORD_ENABLED", "").lower() == "true":
            try:
                from .channels.discord_channel import DiscordChannel
                ch = DiscordChannel(dc_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.DISCORD, ch)
                    ch.start_bot(self._handle_discord_message)
            except Exception as e:
                log.error(f"Failed to configure Discord: {e}")

        # Slack
        sl_config = config.get("slack", {})
        if sl_config.get("enabled") or os.getenv("GATEWAY_SLACK_ENABLED", "").lower() == "true":
            try:
                from .channels.slack_channel import SlackChannel
                ch = SlackChannel(sl_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.SLACK, ch)
            except Exception as e:
                log.error(f"Failed to configure Slack: {e}")

        # WhatsApp
        wa_config = config.get("whatsapp", {})
        if wa_config.get("enabled") or os.getenv("GATEWAY_WHATSAPP_ENABLED", "").lower() == "true":
            try:
                from .channels.whatsapp_channel import WhatsAppChannel
                ch = WhatsAppChannel(wa_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.WHATSAPP, ch)
            except Exception as e:
                log.error(f"Failed to configure WhatsApp: {e}")

        # Microsoft Teams
        teams_config = config.get("teams", {})
        if teams_config.get("enabled") or os.getenv("GATEWAY_TEAMS_ENABLED", "").lower() == "true":
            try:
                from .channels.teams_channel import TeamsChannel
                ch = TeamsChannel(teams_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.TEAMS, ch)
            except Exception as e:
                log.error(f"Failed to configure Teams: {e}")

        # Email
        email_config = config.get("email", {})
        if email_config.get("enabled") or os.getenv("GATEWAY_EMAIL_ENABLED", "").lower() == "true":
            try:
                from .channels.email_channel import EmailChannel
                ch = EmailChannel(email_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.EMAIL, ch)
            except Exception as e:
                log.error(f"Failed to configure Email: {e}")

        # Google Chat
        gchat_config = config.get("google_chat", {})
        if gchat_config.get("enabled") or os.getenv("GATEWAY_GCHAT_ENABLED", "").lower() == "true":
            try:
                from .channels.google_chat_channel import GoogleChatChannel
                ch = GoogleChatChannel(gchat_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.GOOGLE_CHAT, ch)
            except Exception as e:
                log.error(f"Failed to configure Google Chat: {e}")

        # Signal
        signal_config = config.get("signal", {})
        if signal_config.get("enabled") or os.getenv("GATEWAY_SIGNAL_ENABLED", "").lower() == "true":
            try:
                from .channels.signal_channel import SignalChannel
                ch = SignalChannel(signal_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.SIGNAL, ch)
            except Exception as e:
                log.error(f"Failed to configure Signal: {e}")

        # Matrix
        matrix_config = config.get("matrix", {})
        if matrix_config.get("enabled") or os.getenv("GATEWAY_MATRIX_ENABLED", "").lower() == "true":
            try:
                from .channels.matrix_channel import MatrixChannel
                ch = MatrixChannel(matrix_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.MATRIX, ch)
            except Exception as e:
                log.error(f"Failed to configure Matrix: {e}")

        # iMessage
        imsg_config = config.get("imessage", {})
        if imsg_config.get("enabled") or os.getenv("GATEWAY_IMESSAGE_ENABLED", "").lower() == "true":
            try:
                from .channels.imessage_channel import IMessageChannel
                ch = IMessageChannel(imsg_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.IMESSAGE, ch)
            except Exception as e:
                log.error(f"Failed to configure iMessage: {e}")

        # IRC
        irc_config = config.get("irc", {})
        if irc_config.get("enabled") or os.getenv("GATEWAY_IRC_ENABLED", "").lower() == "true":
            try:
                from .channels.irc_channel import IRCChannel
                ch = IRCChannel(irc_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.IRC, ch)
            except Exception as e:
                log.error(f"Failed to configure IRC: {e}")

        # Mattermost
        mm_config = config.get("mattermost", {})
        if mm_config.get("enabled") or os.getenv("GATEWAY_MATTERMOST_ENABLED", "").lower() == "true":
            try:
                from .channels.mattermost_channel import MattermostChannel
                ch = MattermostChannel(mm_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.MATTERMOST, ch)
            except Exception as e:
                log.error(f"Failed to configure Mattermost: {e}")

        # LINE
        line_config = config.get("line", {})
        if line_config.get("enabled") or os.getenv("GATEWAY_LINE_ENABLED", "").lower() == "true":
            try:
                from .channels.line_channel import LINEChannel
                ch = LINEChannel(line_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.LINE, ch)
            except Exception as e:
                log.error(f"Failed to configure LINE: {e}")

        # Twitch
        twitch_config = config.get("twitch", {})
        if twitch_config.get("enabled") or os.getenv("GATEWAY_TWITCH_ENABLED", "").lower() == "true":
            try:
                from .channels.twitch_channel import TwitchChannel
                ch = TwitchChannel(twitch_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.TWITCH, ch)
            except Exception as e:
                log.error(f"Failed to configure Twitch: {e}")

        # Facebook Messenger
        msger_config = config.get("messenger", {})
        if msger_config.get("enabled") or os.getenv("GATEWAY_MESSENGER_ENABLED", "").lower() == "true":
            try:
                from .channels.messenger_channel import MessengerChannel
                ch = MessengerChannel(msger_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.MESSENGER, ch)
            except Exception as e:
                log.error(f"Failed to configure Messenger: {e}")

        # Twitter / X
        tw_config = config.get("twitter", {})
        if tw_config.get("enabled") or os.getenv("GATEWAY_TWITTER_ENABLED", "").lower() == "true":
            try:
                from .channels.twitter_channel import TwitterChannel
                ch = TwitterChannel(tw_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.TWITTER, ch)
            except Exception as e:
                log.error(f"Failed to configure Twitter: {e}")

        # Reddit
        reddit_config = config.get("reddit", {})
        if reddit_config.get("enabled") or os.getenv("GATEWAY_REDDIT_ENABLED", "").lower() == "true":
            try:
                from .channels.reddit_channel import RedditChannel
                ch = RedditChannel(reddit_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.REDDIT, ch)
            except Exception as e:
                log.error(f"Failed to configure Reddit: {e}")

        # Generic Webhook
        wh_config = config.get("webhook", {})
        if wh_config.get("enabled") or os.getenv("GATEWAY_WEBHOOK_ENABLED", "").lower() == "true":
            try:
                from .channels.webhook_channel import WebhookChannel
                ch = WebhookChannel(wh_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.WEBHOOK, ch)
            except Exception as e:
                log.error(f"Failed to configure Webhook: {e}")

        # Nostr
        nostr_config = config.get("nostr", {})
        if nostr_config.get("enabled") or os.getenv("GATEWAY_NOSTR_ENABLED", "").lower() == "true":
            try:
                from .channels.nostr_channel import NostrChannel
                ch = NostrChannel(nostr_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.NOSTR, ch)
            except Exception as e:
                log.error(f"Failed to configure Nostr: {e}")

        # WebChat
        wc_config = config.get("webchat", {})
        if wc_config.get("enabled") or os.getenv("GATEWAY_WEBCHAT_ENABLED", "").lower() == "true":
            try:
                from .channels.webchat_channel import WebChatChannel
                ch = WebChatChannel(wc_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.WEBCHAT, ch)
            except Exception as e:
                log.error(f"Failed to configure WebChat: {e}")

        # Feishu / Lark
        feishu_config = config.get("feishu", {})
        if feishu_config.get("enabled") or os.getenv("GATEWAY_FEISHU_ENABLED", "").lower() == "true":
            try:
                from .channels.feishu_channel import FeishuChannel
                ch = FeishuChannel(feishu_config)
                if ch.is_configured():
                    self.register_channel(ChannelType.FEISHU, ch)
            except Exception as e:
                log.error(f"Failed to configure Feishu: {e}")

        enabled = [ct.value for ct in self.channels]
        log.info(f"Gateway channels: {enabled or 'none'}")

    def process_inbound(self, channel_type: ChannelType, flask_request) -> Dict[str, Any]:
        """Full inbound processing pipeline."""
        channel = self.channels.get(channel_type)
        if not channel or not channel.is_configured():
            return {"error": "Channel not configured", "webhook_response": ""}

        if not channel.validate_webhook(flask_request):
            return {"error": "Invalid signature", "webhook_response": ""}

        msg = channel.parse_inbound(flask_request)
        if not msg:
            return {"skipped": True, "webhook_response": ""}

        response_text = self._process_message(msg)
        webhook_resp = channel.format_webhook_response(response_text, msg)

        # Send async reply for channels that don't reply inline via webhook response
        _async_channels = (
            ChannelType.TELEGRAM, ChannelType.SLACK, ChannelType.TEAMS,
            ChannelType.SIGNAL, ChannelType.MATRIX, ChannelType.GOOGLE_CHAT,
            ChannelType.MATTERMOST, ChannelType.LINE, ChannelType.MESSENGER,
            ChannelType.TWITTER, ChannelType.REDDIT, ChannelType.NOSTR,
            ChannelType.FEISHU,
        )
        if channel_type in _async_channels:
            metadata = msg.channel_metadata
            channel.send_message(
                metadata.get("chat_id", msg.sender_id),
                response_text,
                metadata,
            )

        return {
            "success": True,
            "response": response_text,
            "webhook_response": webhook_resp,
        }

    def _handle_discord_message(self, msg: GatewayMessage) -> Optional[str]:
        return self._process_message(msg)

    def _process_message(self, msg: GatewayMessage) -> str:
        """Route message to agent (multi-agent or single-agent)."""
        agent_name = "default"

        if self._pool and self._router:
            # Multi-agent routing
            agent_name = self._router.route(msg)
            try:
                agent = self._pool.get_agent(agent_name, sender_id=msg.sender_id)
            except ValueError as e:
                log.error(f"Agent pool error: {e}")
                return "Agent not configured."
        elif self.agent:
            agent = self.agent
        else:
            return "Agent not configured."

        try:
            response_text = agent.chat(msg.text)
        except Exception as e:
            log.error(f"Agent error: {e}", exc_info=True)
            response_text = "Something went wrong. Try again?"

        log.info(f"[{msg.channel.value}:{agent_name}] {msg.sender_id}: "
                 f"{msg.text[:50]}... -> {response_text[:50]}...")
        return response_text

    def send_proactive(self, channel_type: ChannelType, recipient_id: str, text: str,
                       metadata: dict = None) -> Dict[str, Any]:
        """Send an agent-initiated message."""
        channel = self.channels.get(channel_type)
        if not channel or not channel.is_configured():
            return {"success": False, "error": f"Channel {channel_type.value} not configured"}
        return channel.send_message(recipient_id, text, metadata)

    def get_status(self) -> Dict[str, Any]:
        return {
            "channels": {ct.value: {"enabled": ch.is_configured()} for ct, ch in self.channels.items()},
            "agent": self.agent.provider.name() if self.agent else "not set",
        }
