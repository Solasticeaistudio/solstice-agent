"""
Configuration
=============
Load settings from config.yaml, env vars, or CLI args.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Any
from pathlib import Path

log = logging.getLogger("solstice.config")

CONFIG_FILENAME = "solstice-agent.yaml"
CONFIG_SEARCH_PATHS = [
    Path.cwd() / CONFIG_FILENAME,
    Path.home() / ".config" / "solstice-agent" / CONFIG_FILENAME,
    Path.home() / ".solstice-agent" / CONFIG_FILENAME,
]


@dataclass
class Config:
    """Agent configuration."""
    # LLM provider
    provider: str = "openai"  # openai, anthropic, gemini, ollama
    model: str = ""           # Provider-specific model name
    api_key: str = ""         # API key (or set via env var)

    # Agent
    personality_name: str = "default"
    temperature: float = 0.7
    max_tokens: int = 4096

    # Tools
    enable_terminal: bool = True
    enable_web: bool = True
    enable_skills: bool = True
    enable_cron: bool = True
    enable_registry: bool = True

    # Gateway
    gateway_enabled: bool = False
    gateway_channels: Dict[str, Any] = field(default_factory=dict)

    # Outreach
    outreach_booking_link: str = ""
    outreach_booking_cta: str = "If helpful, you can grab a time here:"
    outreach_booking_label: str = "booking link"

    # Multi-agent
    agents: Dict[str, Any] = field(default_factory=dict)
    routing: Dict[str, Any] = field(default_factory=dict)

    # Ollama
    ollama_base_url: str = "http://localhost:11434"

    # OpenAI-compatible
    base_url: str = ""  # For custom OpenAI-compatible endpoints

    @classmethod
    def load(cls, path: str = None) -> "Config":
        """Load config from YAML file, env vars, or defaults."""
        config = cls()

        # Try YAML file
        yaml_path = Path(path) if path else None
        if not yaml_path:
            for search_path in CONFIG_SEARCH_PATHS:
                if search_path.exists():
                    yaml_path = search_path
                    break

        if yaml_path and yaml_path.exists():
            config._load_yaml(yaml_path)
            log.info(f"Loaded config from {yaml_path}")

        # Env vars override YAML
        config._load_env()

        # Set defaults for model if not specified
        if not config.model:
            config.model = {
                "openai": "gpt-4o",
                "anthropic": "claude-sonnet-4-5-20250929",
                "gemini": "gemini-2.5-flash",
                "ollama": "llama3.1",
            }.get(config.provider, "gpt-4o")

        return config

    def _load_yaml(self, path: Path):
        """Load from YAML file."""
        try:
            import yaml
        except ImportError:
            log.warning("PyYAML not installed. Config file ignored. pip install pyyaml")
            return

        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}

        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def _load_env(self):
        """Override with environment variables."""
        # Provider-specific key detection
        if os.getenv("OPENAI_API_KEY") and not os.getenv("SOLSTICE_PROVIDER"):
            self.provider = "openai"
            self.api_key = os.getenv("OPENAI_API_KEY", "")
        elif os.getenv("ANTHROPIC_API_KEY") and not os.getenv("SOLSTICE_PROVIDER"):
            self.provider = "anthropic"
            self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        elif os.getenv("GEMINI_API_KEY") and not os.getenv("SOLSTICE_PROVIDER"):
            self.provider = "gemini"
            self.api_key = os.getenv("GEMINI_API_KEY", "")
        elif os.getenv("GOOGLE_API_KEY") and not os.getenv("SOLSTICE_PROVIDER"):
            self.provider = "gemini"
            self.api_key = os.getenv("GOOGLE_API_KEY", "")

        # Explicit overrides
        if os.getenv("SOLSTICE_PROVIDER"):
            self.provider = os.getenv("SOLSTICE_PROVIDER", self.provider)
        if os.getenv("SOLSTICE_API_KEY"):
            self.api_key = os.getenv("SOLSTICE_API_KEY", self.api_key)
        if os.getenv("SOLSTICE_MODEL"):
            self.model = os.getenv("SOLSTICE_MODEL", self.model)
        if os.getenv("SOLSTICE_OUTREACH_BOOKING_LINK"):
            self.outreach_booking_link = os.getenv("SOLSTICE_OUTREACH_BOOKING_LINK", self.outreach_booking_link)
        if os.getenv("SOLSTICE_OUTREACH_BOOKING_CTA"):
            self.outreach_booking_cta = os.getenv("SOLSTICE_OUTREACH_BOOKING_CTA", self.outreach_booking_cta)
        if os.getenv("SOLSTICE_OUTREACH_BOOKING_LABEL"):
            self.outreach_booking_label = os.getenv("SOLSTICE_OUTREACH_BOOKING_LABEL", self.outreach_booking_label)

    def create_provider(self):
        """Create an LLM provider from config."""
        from .agent.providers import (
            OpenAIProvider, AnthropicProvider, GeminiProvider, OllamaProvider
        )

        kwargs = {}
        if self.base_url:
            kwargs["base_url"] = self.base_url

        if self.provider == "openai":
            return OpenAIProvider(api_key=self.api_key, model=self.model, **kwargs)
        elif self.provider == "anthropic":
            return AnthropicProvider(api_key=self.api_key, model=self.model, **kwargs)
        elif self.provider == "gemini":
            return GeminiProvider(api_key=self.api_key, model=self.model, **kwargs)
        elif self.provider == "ollama":
            kwargs["base_url"] = self.ollama_base_url
            return OllamaProvider(api_key="", model=self.model, **kwargs)
        else:
            raise ValueError(f"Unknown provider: {self.provider}. "
                             f"Valid: openai, anthropic, gemini, ollama")

    def has_multi_agent(self) -> bool:
        """Check if multi-agent routing is configured."""
        return bool(self.agents)

    def get_agent_configs(self):
        """Parse agents dict into AgentConfig objects."""
        from .agent.router import AgentConfig
        configs = {}
        for name, data in self.agents.items():
            if isinstance(data, dict):
                configs[name] = AgentConfig.from_dict(name, data)
            else:
                configs[name] = AgentConfig(name=name)
        return configs

    def get_routing_config(self) -> Dict[str, Any]:
        """Get routing configuration dict."""
        return self.routing


def find_config_path(path: str = None) -> Path | None:
    """Return the first existing config path, if any."""
    yaml_path = Path(path) if path else None
    if yaml_path and yaml_path.exists():
        return yaml_path
    for search_path in CONFIG_SEARCH_PATHS:
        if search_path.exists():
            return search_path
    return None


def default_config_path(path: str = None) -> Path:
    """Return the preferred writable config path for setup."""
    if path:
        return Path(path).expanduser()
    return Path.home() / ".config" / "solstice-agent" / CONFIG_FILENAME


def provider_env_snapshot() -> Dict[str, str]:
    """Return currently set provider-related environment variables."""
    names = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "SOLSTICE_PROVIDER",
        "SOLSTICE_API_KEY",
        "SOLSTICE_MODEL",
    ]
    return {name: os.getenv(name, "") for name in names if os.getenv(name)}
