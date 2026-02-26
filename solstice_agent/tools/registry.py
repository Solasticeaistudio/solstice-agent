"""
Tool Registry
=============
Central registry for all agent tools. Handles registration, schema validation,
and bulk loading of built-in tool sets.
"""

import logging
from typing import Dict, Callable, Any, List

log = logging.getLogger("solstice.tools")


class ToolRegistry:
    """
    Manage tools for an agent.

    Usage:
        registry = ToolRegistry()
        registry.load_builtins()  # file ops, terminal, web search
        registry.apply(agent)     # register all tools with the agent
    """

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, handler: Callable, schema: Dict[str, Any]):
        """Register a single tool."""
        self._handlers[name] = handler
        self._schemas[name] = schema
        log.debug(f"Tool registered: {name}")

    def load_builtins(
        self,
        enable_terminal: bool = True,
        enable_web: bool = True,
        enable_blackbox: bool = True,
        enable_browser: bool = True,
        enable_voice: bool = True,
        enable_memory: bool = True,
        enable_skills: bool = True,
        enable_cron: bool = True,
        enable_registry: bool = True,
        enable_screen: bool = True,
        enable_docker: bool = True,
        enable_voice_continuous: bool = True,
        enable_presence: bool = True,
        enable_recording: bool = True,
        enable_outreach: bool = True,
        enable_camunda: bool = True,
    ):
        """Load all built-in tool sets."""
        from .file_ops import register_file_tools
        from .terminal import register_terminal_tools
        from .web import register_web_tools
        from .blackbox import register_blackbox_tools
        from .browser import register_browser_tools
        from .voice import register_voice_tools
        from ..agent.memory import register_memory_tools
        from ..agent.skills import register_skill_tools
        from ..agent.scheduler import register_cron_tools
        from .api_registry import register_registry_tools

        register_file_tools(self)

        if enable_terminal:
            register_terminal_tools(self)

        if enable_web:
            register_web_tools(self)

        if enable_blackbox:
            register_blackbox_tools(self)

        if enable_browser:
            register_browser_tools(self)

        if enable_voice:
            register_voice_tools(self)

        if enable_memory:
            register_memory_tools(self)

        if enable_skills:
            register_skill_tools(self)

        if enable_cron:
            register_cron_tools(self)

        if enable_registry:
            register_registry_tools(self)

        if enable_screen:
            from .screen import register_screen_tools
            register_screen_tools(self)

        if enable_docker:
            from .docker_sandbox import register_docker_tools
            register_docker_tools(self)

        if enable_voice_continuous:
            from .voice_continuous import register_voice_continuous_tools
            register_voice_continuous_tools(self)

        if enable_presence:
            from .presence import register_presence_tools
            register_presence_tools(self)

        if enable_recording:
            from .recording import register_recording_tools
            register_recording_tools(self)

        if enable_outreach:
            from ..outreach.tools import register_outreach_tools
            register_outreach_tools(self)

        if enable_camunda:
            from .camunda import register_camunda_tools
            register_camunda_tools(self)

        log.info(f"Loaded {len(self._handlers)} built-in tools")

    def apply(self, agent):
        """Register all tools with an Agent instance."""
        for name, handler in self._handlers.items():
            agent.register_tool(name, handler, self._schemas[name])

    def list_tools(self) -> List[str]:
        """Get names of all registered tools."""
        return list(self._handlers.keys())

    def get_schema(self, name: str) -> Dict[str, Any]:
        """Get schema for a specific tool."""
        return self._schemas.get(name, {})
