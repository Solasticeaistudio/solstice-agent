"""
OpenAI Provider
===============
GPT-4o, GPT-4o-mini, o1, o3, etc.
Requires: pip install openai
"""

import json
import logging
from typing import Generator, List, Dict, Any, Optional

from .base import BaseLLMProvider, LLMResponse, StreamEvent

log = logging.getLogger("solstice.provider.openai")


class OpenAIProvider(BaseLLMProvider):

    def __init__(self, api_key: str = "", model: str = "gpt-4o", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self._base_url = kwargs.get("base_url")  # For OpenAI-compatible APIs
        self._client = None

    def _get_client(self):
        """Get or create the OpenAI client (reused across calls)."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError("OpenAI provider requires: pip install openai")
            client_kwargs = {"api_key": self.api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            self._client = OpenAI(**client_kwargs)
        return self._client

    def name(self) -> str:
        return f"OpenAI ({self.model})"

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = self._get_client()

        # Convert multimodal content blocks to OpenAI format
        formatted = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                parts = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        parts.append({"type": "text", "text": block["text"]})
                    elif block.get("type") == "image":
                        src = block.get("source", {})
                        parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{src['media_type']};base64,{src['data']}",
                            },
                        })
                    else:
                        parts.append(block)
                formatted.append({"role": msg["role"], "content": parts})
            else:
                formatted.append(msg)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
                for t in tools
            ]

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })

        return LLMResponse(
            text=choice.message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
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
        client = self._get_client()

        # Reuse the same message formatting as chat()
        formatted = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                parts = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        parts.append({"type": "text", "text": block["text"]})
                    elif block.get("type") == "image":
                        src = block.get("source", {})
                        parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{src['media_type']};base64,{src['data']}",
                            },
                        })
                    else:
                        parts.append(block)
                formatted.append({"role": msg["role"], "content": parts})
            else:
                formatted.append(msg)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
                for t in tools
            ]

        stream = client.chat.completions.create(**kwargs)

        # Accumulate tool calls across chunks (they arrive incrementally)
        pending_tool_calls: Dict[int, Dict[str, Any]] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            # Text content
            if delta.content:
                yield StreamEvent(type="text", text=delta.content)

            # Tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in pending_tool_calls:
                        pending_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    tc = pending_tool_calls[idx]
                    if tc_delta.id:
                        tc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc["arguments"] += tc_delta.function.arguments

            # Check for finish
            finish = chunk.choices[0].finish_reason if chunk.choices else None
            if finish == "tool_calls" and pending_tool_calls:
                # Parse accumulated JSON arguments
                tool_calls = []
                for idx in sorted(pending_tool_calls):
                    tc = pending_tool_calls[idx]
                    try:
                        tc["arguments"] = json.loads(tc["arguments"])
                    except (json.JSONDecodeError, TypeError):
                        tc["arguments"] = {}
                    tool_calls.append(tc)
                yield StreamEvent(type="tool_calls", tool_calls=tool_calls)

        yield StreamEvent(type="done")
