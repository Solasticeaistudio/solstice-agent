"""Built-in tools — file ops, terminal, web search, blackbox, browser, voice, memory, api registry."""
from .registry import ToolRegistry
from .file_ops import register_file_tools
from .terminal import register_terminal_tools
from .web import register_web_tools
from .blackbox import register_blackbox_tools
from .browser import register_browser_tools
from .voice import register_voice_tools
from .api_registry import register_registry_tools

__all__ = [
    "ToolRegistry",
    "register_file_tools",
    "register_terminal_tools",
    "register_web_tools",
    "register_blackbox_tools",
    "register_browser_tools",
    "register_voice_tools",
    "register_registry_tools",
]
