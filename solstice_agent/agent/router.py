"""
Multi-Agent Router
==================
Routes messages to named agents with per-sender isolation.

Components:
  AgentConfig  — Per-agent configuration (provider, personality, tool flags)
  AgentPool    — Named agent instances with LRU caching
  AgentRouter  — Message → agent name mapping (4 strategies)

Usage:
    pool = AgentPool(configs, global_config)
    router = AgentRouter(strategy="channel", rules={"discord": "coder"})

    agent_name = router.route(msg)
    agent = pool.get_agent(agent_name, sender_id=msg.sender_id)
    response = agent.chat(msg.text)
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from .core import Agent

log = logging.getLogger("solstice.router")

# Default tool flags — all enabled
_DEFAULT_TOOL_FLAGS = {
    "enable_terminal": True,
    "enable_web": True,
    "enable_blackbox": True,
    "enable_browser": True,
    "enable_voice": True,
    "enable_memory": True,
    "enable_skills": True,
    "enable_cron": True,
}


@dataclass
class AgentConfig:
    """Per-agent configuration. Empty fields inherit from global config."""
    name: str = "default"
    provider: str = ""
    model: str = ""
    api_key: str = ""
    temperature: float = 0.0      # 0.0 = inherit global
    personality_spec: Any = "default"  # str name or dict for inline
    tool_flags: Dict[str, bool] = field(default_factory=dict)

    def resolved_tool_flags(self) -> Dict[str, bool]:
        """Return tool flags with defaults filled in."""
        flags = dict(_DEFAULT_TOOL_FLAGS)
        flags.update(self.tool_flags)
        return flags

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "AgentConfig":
        """Parse an agent config from a YAML dict."""
        tools = data.get("tools", {})
        personality = data.get("personality", "default")

        return cls(
            name=name,
            provider=data.get("provider", ""),
            model=data.get("model", ""),
            api_key=data.get("api_key", ""),
            temperature=float(data.get("temperature", 0.0)),
            personality_spec=personality,
            tool_flags=tools,
        )


class AgentPool:
    """
    Manages named agent instances with per-sender isolation.

    Each (agent_name, sender_id) pair gets its own Agent with independent
    conversation history. LRU eviction prevents unbounded memory growth.
    """

    MAX_CACHE = 200

    def __init__(self, agent_configs: Dict[str, AgentConfig], global_config=None):
        """
        Args:
            agent_configs: Dict of name → AgentConfig
            global_config: The global Config instance for fallback values
        """
        self._configs = agent_configs
        self._global = global_config
        self._agents: OrderedDict = OrderedDict()

    def get_agent(self, name: str, sender_id: str = "") -> "Agent":
        """
        Get or create an agent for (name, sender_id).
        Per-sender isolation: each sender gets their own agent instance.
        """
        if name not in self._configs:
            log.warning(f"Agent '{name}' not found, falling back to 'default'")
            name = "default"
            if name not in self._configs:
                raise ValueError("No 'default' agent configured")

        key = f"{name}:{sender_id}" if sender_id else name
        if key in self._agents:
            self._agents.move_to_end(key)
            return self._agents[key]

        agent = self._create_agent(name)
        self._agents[key] = agent
        self._evict_if_needed()
        log.debug(f"Created agent '{name}' for sender '{sender_id or 'cli'}'")
        return agent

    def list_agents(self) -> List[str]:
        """List configured agent names."""
        return list(self._configs.keys())

    def get_config(self, name: str) -> Optional[AgentConfig]:
        """Get config for a named agent."""
        return self._configs.get(name)

    def active_count(self) -> int:
        """Number of active (cached) agent instances."""
        return len(self._agents)

    def _create_agent(self, name: str) -> "Agent":
        """Create a fresh Agent from named config."""
        from .core import Agent
        from .compactor import ContextCompactor, CompactorConfig
        from .skills import _get_loader
        from .personalities import resolve_personality
        from ..tools.registry import ToolRegistry

        cfg = self._configs[name]
        provider = self._resolve_provider(cfg)
        personality = resolve_personality(cfg.personality_spec)
        temperature = cfg.temperature if cfg.temperature > 0 else self._global_temperature()

        # Compactor
        model_name = cfg.model or self._global_model()
        compactor = ContextCompactor(
            provider=provider,
            config=CompactorConfig(model_name=model_name),
        )

        # Skills
        skill_loader = _get_loader()

        agent = Agent(
            provider=provider,
            personality=personality,
            temperature=temperature,
            skill_loader=skill_loader,
            compactor=compactor,
        )

        # Tools — per-agent flags
        registry = ToolRegistry()
        registry.load_builtins(**cfg.resolved_tool_flags())
        registry.apply(agent)

        return agent

    def _resolve_provider(self, cfg: AgentConfig):
        """Create an LLM provider for this agent config."""
        from ..config import Config

        provider_name = cfg.provider or (self._global.provider if self._global else "openai")
        model_name = cfg.model or (self._global.model if self._global else "")
        api_key = cfg.api_key or (self._global.api_key if self._global else "")

        # Create a temporary Config to use its provider factory
        temp = Config(
            provider=provider_name,
            model=model_name,
            api_key=api_key,
        )
        if not temp.model:
            temp.model = {
                "openai": "gpt-4o",
                "anthropic": "claude-sonnet-4-5-20250929",
                "gemini": "gemini-2.5-flash",
                "ollama": "llama3.1",
            }.get(temp.provider, "gpt-4o")

        if self._global and self._global.base_url and not cfg.provider:
            temp.base_url = self._global.base_url
        if self._global and self._global.ollama_base_url:
            temp.ollama_base_url = self._global.ollama_base_url

        return temp.create_provider()

    def _global_temperature(self) -> float:
        return self._global.temperature if self._global else 0.7

    def _global_model(self) -> str:
        return self._global.model if self._global else ""

    def _evict_if_needed(self):
        """LRU eviction when cache exceeds MAX_CACHE."""
        while len(self._agents) > self.MAX_CACHE:
            evicted_key, _ = self._agents.popitem(last=False)
            log.info(f"Evicted agent: {evicted_key}")


class AgentRouter:
    """
    Routes messages to named agents based on configurable strategies.

    Strategies:
      sender  — Map sender IDs to agents
      channel — Map channel types to agents
      content — Regex matching on message text
      prefix  — Command prefix (strips prefix from message)
    """

    VALID_STRATEGIES = ("sender", "channel", "content", "prefix")

    def __init__(
        self,
        strategy: str = "channel",
        rules: Optional[Dict[str, str]] = None,
        default: str = "default",
    ):
        if strategy not in self.VALID_STRATEGIES:
            raise ValueError(
                f"Invalid routing strategy '{strategy}'. "
                f"Valid: {', '.join(self.VALID_STRATEGIES)}"
            )

        self.strategy = strategy
        self.rules = rules or {}
        self.default = default

        # Pre-compile regex patterns for content strategy
        self._compiled_rules: List[Tuple[re.Pattern, str]] = []
        if strategy == "content":
            for pattern, agent_name in self.rules.items():
                try:
                    self._compiled_rules.append(
                        (re.compile(pattern, re.IGNORECASE), agent_name)
                    )
                except re.error as e:
                    log.warning(f"Invalid content routing pattern '{pattern}': {e}")

    def route(self, msg) -> str:
        """
        Determine which agent should handle this message.

        Args:
            msg: A GatewayMessage (or any object with sender_id, channel, text attrs).
                 For CLI use, pass a simple object or use route_direct().

        Returns:
            Agent name string.
        """
        if self.strategy == "sender":
            sender = getattr(msg, "sender_id", "")
            return self.rules.get(sender, self.default)

        elif self.strategy == "channel":
            channel = getattr(msg, "channel", None)
            channel_str = channel.value if hasattr(channel, "value") else str(channel)
            return self.rules.get(channel_str, self.default)

        elif self.strategy == "content":
            text = getattr(msg, "text", "")
            for pattern, agent_name in self._compiled_rules:
                if pattern.search(text):
                    return agent_name
            return self.default

        elif self.strategy == "prefix":
            text = getattr(msg, "text", "")
            for prefix, agent_name in self.rules.items():
                if text.startswith(prefix):
                    # Strip prefix from message
                    if hasattr(msg, "text"):
                        msg.text = text[len(prefix):].strip()
                    return agent_name
            return self.default

        return self.default

    @classmethod
    def from_config(cls, routing_config: dict) -> "AgentRouter":
        """Create a router from a config dict."""
        return cls(
            strategy=routing_config.get("strategy", "channel"),
            rules=routing_config.get("rules", {}),
            default=routing_config.get("default", "default"),
        )
