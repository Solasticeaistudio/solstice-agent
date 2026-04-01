"""
Gateway Manager — Standalone
=============================
Routes inbound messages to the framework's Agent (not Solstice services).
Manages per-sender conversation history and proactive outbound.
"""

import os
import logging
import threading
from typing import Dict, List, Any, Optional

from ..onboarding import guided_quickstart_menu, guided_quickstart_prompt
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
        self._subagent_followers: Dict[str, bool] = {}
        self._quickstart_pending: Dict[str, bool] = {}

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
        lowered = (msg.text or "").strip().lower()
        identity = msg.routing_identity()
        if lowered == "/tasks":
            from ..agent.tasks import task_list
            return task_list()

        agent_name = "default"

        if self._pool and self._router:
            # Multi-agent routing
            agent_name = self._router.route(msg)
            try:
                agent = self._pool.get_agent(agent_name, sender_id=msg.routing_identity())
            except ValueError as e:
                log.error(f"Agent pool error: {e}")
                return "Agent not configured."
        elif self.agent:
            agent = self.agent
        else:
            return "Agent not configured."

        if lowered == "/start":
            self._quickstart_pending[identity] = True
            return guided_quickstart_menu()
        if lowered == "/subagents" and "subagent_list" in getattr(agent, "_tools", {}):
            return agent._tools["subagent_list"]()
        if lowered == "/workflows" and "workflow_list" in getattr(agent, "_tools", {}):
            return agent._tools["workflow_list"]()
        if lowered.startswith("/workflow ") and "workflow_status" in getattr(agent, "_tools", {}):
            return agent._tools["workflow_status"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/workflow-events ") and "workflow_events" in getattr(agent, "_tools", {}):
            return agent._tools["workflow_events"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/workflow-export ") and "workflow_export" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 2:
                snapshot_id = parts[2] if len(parts) >= 3 else ""
                return agent._tools["workflow_export"](parts[1], snapshot_id)
        if lowered.startswith("/workflow-snapshot ") and "workflow_snapshot" in getattr(agent, "_tools", {}):
            try:
                _, workflow_id, label = msg.text.split(" ", 2)
            except ValueError:
                workflow_id = msg.text.split(" ", 1)[1].strip()
                label = ""
            return agent._tools["workflow_snapshot"](workflow_id, label)
        if lowered.startswith("/retry-workflow-node ") and "workflow_retry_node" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 3:
                return agent._tools["workflow_retry_node"](parts[1], parts[2])
        if lowered.startswith("/retry-workflow-branch ") and "workflow_retry_branch" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 3:
                return agent._tools["workflow_retry_branch"](parts[1], parts[2])
        if lowered.startswith("/disable-workflow-node ") and "workflow_disable_node" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 3:
                return agent._tools["workflow_disable_node"](parts[1], parts[2])
        if lowered.startswith("/enable-workflow-node ") and "workflow_enable_node" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 3:
                return agent._tools["workflow_enable_node"](parts[1], parts[2])
        if lowered.startswith("/remove-workflow-node ") and "workflow_remove_node" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 3:
                return agent._tools["workflow_remove_node"](parts[1], parts[2])
        if lowered.startswith("/rewire-workflow ") and "workflow_rewire_dependency" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 5:
                policy = parts[5] if len(parts) >= 6 else "block"
                return agent._tools["workflow_rewire_dependency"](parts[1], parts[2], parts[3], parts[4], policy)
        if lowered.startswith("/set-workflow-priority ") and "workflow_set_priority" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 4:
                return agent._tools["workflow_set_priority"](parts[1], parts[2], int(parts[3]))
        if lowered.startswith("/set-workflow-edge ") and "workflow_update_edge_policy" in getattr(agent, "_tools", {}):
            parts = msg.text.split()
            if len(parts) >= 5:
                return agent._tools["workflow_update_edge_policy"](parts[1], parts[2], parts[3], parts[4])
        if lowered.startswith("/cancel-workflow ") and "workflow_cancel" in getattr(agent, "_tools", {}):
            return agent._tools["workflow_cancel"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/resume-workflow ") and "workflow_resume" in getattr(agent, "_tools", {}):
            return agent._tools["workflow_resume"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/submit-workflow ") and "submit_workflow" in getattr(agent, "_tools", {}):
            return agent._tools["submit_workflow"](msg.text.split(" ", 1)[1].strip(), "")
        if lowered.startswith("/add-workflow-node ") and "workflow_add_node" in getattr(agent, "_tools", {}):
            try:
                _, workflow_id, node_id, prompt = msg.text.split(" ", 3)
            except ValueError:
                return "Usage: /add-workflow-node <workflow_id> <node_id> <prompt>"
            return agent._tools["workflow_add_node"](workflow_id, node_id, prompt)
        if lowered == "/subagent-graph" and "subagent_graph" in getattr(agent, "_tools", {}):
            return agent._tools["subagent_graph"]("")
        if lowered.startswith("/subagent-graph ") and "subagent_graph" in getattr(agent, "_tools", {}):
            return agent._tools["subagent_graph"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/subagent ") and "subagent_result" in getattr(agent, "_tools", {}):
            return agent._tools["subagent_result"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/subagent-progress ") and "subagent_progress" in getattr(agent, "_tools", {}):
            return agent._tools["subagent_progress"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/resume-subagent ") and "resume_subagent" in getattr(agent, "_tools", {}):
            return agent._tools["resume_subagent"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/cancel-subagent ") and "cancel_subagent" in getattr(agent, "_tools", {}):
            return agent._tools["cancel_subagent"](msg.text.split(" ", 1)[1].strip())
        if lowered.startswith("/follow-subagent ") and "subagent_progress" in getattr(agent, "_tools", {}):
            run_id = msg.text.split(" ", 1)[1].strip()
            self._follow_subagent_progress(msg, run_id)
            return f"Following sub-agent {run_id}. Progress updates will be pushed here."
        if lowered.startswith("/follow-workflow ") and "workflow_events" in getattr(agent, "_tools", {}):
            workflow_id = msg.text.split(" ", 1)[1].strip()
            self._follow_workflow_events(msg, workflow_id)
            return f"Following workflow {workflow_id}. Event updates will be pushed here."

        quickstart_prompt = guided_quickstart_prompt(msg.text, allow_fuzzy=False)
        if not quickstart_prompt and self._quickstart_pending.get(identity):
            quickstart_prompt = guided_quickstart_prompt(msg.text, allow_fuzzy=True)
        if quickstart_prompt:
            self._quickstart_pending.pop(identity, None)
            try:
                response_text = agent.chat(quickstart_prompt)
            except Exception as e:
                log.error(f"Agent error: {e}", exc_info=True)
                response_text = "Something went wrong. Try again?"
            log.info(
                f"[{msg.channel.value}:{agent_name}] {msg.sender_id}: "
                f"{msg.text[:50]}... -> {response_text[:50]}..."
            )
            return response_text
        if self._quickstart_pending.get(identity) and not lowered.startswith("/"):
            self._quickstart_pending.pop(identity, None)

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
        task_summary = ""
        try:
            from ..agent.tasks import _get_board
            task_summary = f"{len(_get_board().list())} tracked"
        except Exception:
            task_summary = "unavailable"

        subagent_summary = "unavailable"
        if self.agent and "subagent_list" in getattr(self.agent, "_tools", {}):
            try:
                from ..agent.subagents import _get_manager
                subagent_summary = f"{len(_get_manager().list())} runs"
            except Exception:
                pass
        return {
            "channels": {ct.value: {"enabled": ch.is_configured()} for ct, ch in self.channels.items()},
            "agent": self.agent.provider.name() if self.agent else "not set",
            "tasks": task_summary,
            "subagents": subagent_summary,
        }

    def _follow_subagent_progress(self, msg: GatewayMessage, run_id: str):
        key = f"{msg.channel.value}:{msg.sender_id}:{run_id}"
        if self._subagent_followers.get(key):
            return
        self._subagent_followers[key] = True

        def _worker():
            try:
                from ..agent.subagents import _get_manager

                manager = _get_manager()
                watcher = manager.subscribe(run_id)
                channel = self.channels.get(msg.channel)
                if not channel or not channel.is_configured():
                    return
                recipient = msg.channel_metadata.get("chat_id", msg.sender_id)
                while True:
                    try:
                        event = watcher.get(timeout=15)
                    except Exception:
                        run = manager.get(run_id)
                        if run and run.status in {"completed", "failed", "interrupted", "cancelled"}:
                            break
                        continue
                    event_type = event.get("type", "progress")
                    message = event.get("message", event_type)
                    channel.send_message(recipient, f"[{run_id}] {message}", {**msg.channel_metadata, "event": event})
                    run = manager.get(run_id)
                    if run and run.status in {"completed", "failed", "interrupted", "cancelled"} and run.events and run.events[-1] == event:
                        channel.send_message(recipient, f"[{run_id}] finished with status {run.status}", msg.channel_metadata)
                        break
                manager.unsubscribe(run_id, watcher)
            finally:
                self._subagent_followers.pop(key, None)

        threading.Thread(target=_worker, daemon=True).start()

    def _follow_workflow_events(self, msg: GatewayMessage, workflow_id: str):
        key = f"{msg.channel.value}:{msg.sender_id}:workflow:{workflow_id}"
        if self._subagent_followers.get(key):
            return
        self._subagent_followers[key] = True

        def _worker():
            try:
                from ..agent.subagents import _get_manager

                manager = _get_manager()
                watcher = manager.subscribe_workflow(workflow_id)
                channel = self.channels.get(msg.channel)
                if not channel or not channel.is_configured():
                    return
                recipient = msg.channel_metadata.get("chat_id", msg.sender_id)
                while True:
                    try:
                        event = watcher.get(timeout=15)
                    except Exception:
                        continue
                    event_type = event.get("type", "workflow")
                    message = event.get("message", event_type)
                    channel.send_message(recipient, f"[{workflow_id}] {message}", {**msg.channel_metadata, "event": event})
                manager.unsubscribe_workflow(workflow_id, watcher)
            finally:
                self._subagent_followers.pop(key, None)

        threading.Thread(target=_worker, daemon=True).start()
