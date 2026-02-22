"""
Anthropic Provider
==================
Claude Opus 4, Sonnet 4.5, Haiku 4.5, etc.
Requires: pip install anthropic
"""

import json
import logging
from typing import Generator, List, Dict, Any, Optional

from .base import BaseLLMProvider, LLMResponse, StreamEvent

log = logging.getLogger("solstice.provider.anthropic")


class AnthropicProvider(BaseLLMProvider):

    def __init__(self, api_key: str = "", model: str = "claude-sonnet-4-5-20250929", **kwargs):
        super().__init__(api_key, model, **kwargs)

    def name(self) -> str:
        return f"Anthropic ({self.model})"

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Anthropic provider requires: pip install anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)

        # Extract system message (Anthropic uses a separate system param)
        # Convert multimodal content blocks to Anthropic format
        system_text = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                content = msg["content"]
                system_text += (content if isinstance(content, str) else str(content)) + "\n"
            elif isinstance(msg.get("content"), list):
                parts = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        parts.append({"type": "text", "text": block["text"]})
                    elif block.get("type") == "image":
                        src = block.get("source", {})
                        parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": src["media_type"],
                                "data": src["data"],
                            },
                        })
                    else:
                        parts.append(block)
                chat_messages.append({"role": msg["role"], "content": parts})
            else:
                chat_messages.append(msg)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_text.strip():
            kwargs["system"] = system_text.strip()

        if tools:
            kwargs["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]

        response = client.messages.create(**kwargs)

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input,
                })

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "end_turn",
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            raw=response,
        )

    def supports_streaming(self) -> bool:
        return True

    def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> Generator[StreamEvent, None, None]:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Anthropic provider requires: pip install anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)

        # Same message formatting as chat()
        system_text = ""
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                content = msg["content"]
                system_text += (content if isinstance(content, str) else str(content)) + "\n"
            elif isinstance(msg.get("content"), list):
                parts = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        parts.append({"type": "text", "text": block["text"]})
                    elif block.get("type") == "image":
                        src = block.get("source", {})
                        parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": src["media_type"],
                                "data": src["data"],
                            },
                        })
                    else:
                        parts.append(block)
                chat_messages.append({"role": msg["role"], "content": parts})
            else:
                chat_messages.append(msg)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_text.strip():
            kwargs["system"] = system_text.strip()

        if tools:
            kwargs["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]

        # Anthropic streaming uses context manager
        pending_tool_calls = []
        current_tool: Optional[Dict[str, Any]] = None
        current_tool_json = ""

        with client.messages.stream(**kwargs) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool = {
                            "id": block.id,
                            "name": block.name,
                            "arguments": {},
                        }
                        current_tool_json = ""

                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield StreamEvent(type="text", text=delta.text)
                    elif delta.type == "input_json_delta":
                        current_tool_json += delta.partial_json

                elif event.type == "content_block_stop":
                    if current_tool is not None:
                        try:
                            current_tool["arguments"] = json.loads(current_tool_json) if current_tool_json else {}
                        except json.JSONDecodeError:
                            current_tool["arguments"] = {}
                        pending_tool_calls.append(current_tool)
                        current_tool = None
                        current_tool_json = ""

                elif event.type == "message_stop":
                    if pending_tool_calls:
                        yield StreamEvent(type="tool_calls", tool_calls=pending_tool_calls)

        yield StreamEvent(type="done")
