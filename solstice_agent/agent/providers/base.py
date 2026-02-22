"""
Base LLM Provider
=================
Abstract interface for all LLM providers. Bring your own keys.
"""

import base64
import mimetypes
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generator, List, Dict, Any, Optional


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    text: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: Dict[str, int] = field(default_factory=dict)
    raw: Any = None


@dataclass
class StreamEvent:
    """A single event from a streaming LLM response."""
    type: str = "text"     # "text", "tool_calls", "done"
    text: str = ""         # Text chunk (for type="text")
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # (for type="tool_calls")
    usage: Dict[str, int] = field(default_factory=dict)  # (for type="done")


def encode_image(path: str) -> tuple:
    """Read an image file and return (base64_data, media_type)."""
    path = os.path.expanduser(path)
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/png"
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, mime


class BaseLLMProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, api_key: str = "", model: str = "", **kwargs):
        self.api_key = api_key
        self.model = model
        self.extra_config = kwargs

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion request with optional tool definitions."""
        pass

    def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[StreamEvent, None, None]:
        """
        Stream a chat completion, yielding StreamEvents as they arrive.

        Default implementation falls back to non-streaming chat() and
        yields the full response as a single event. Override in subclasses
        for true token-by-token streaming.
        """
        response = self.chat(messages, tools, temperature, max_tokens)
        if response.tool_calls:
            yield StreamEvent(type="tool_calls", tool_calls=response.tool_calls)
        if response.text:
            yield StreamEvent(type="text", text=response.text)
        yield StreamEvent(type="done", usage=response.usage)

    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        pass

    def supports_tools(self) -> bool:
        """Whether this provider supports native tool/function calling."""
        return True

    def supports_vision(self) -> bool:
        """Whether this provider supports image inputs."""
        return True

    def supports_streaming(self) -> bool:
        """Whether this provider implements true streaming."""
        return False
