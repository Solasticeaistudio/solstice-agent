"""
Ollama Provider
===============
Run local models — Llama 3, Mistral, Qwen, DeepSeek, etc.
No API key needed. Just install Ollama and pull a model.
Requires: Ollama running at http://localhost:11434
"""

import json
import logging
from typing import Generator, List, Dict, Any, Optional

from .base import BaseLLMProvider, LLMResponse, StreamEvent

log = logging.getLogger("solstice.provider.ollama")


class OllamaProvider(BaseLLMProvider):

    def __init__(self, api_key: str = "", model: str = "llama3.1", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self._base_url = kwargs.get("base_url", "http://localhost:11434")

    def name(self) -> str:
        return f"Ollama ({self.model})"

    def supports_tools(self) -> bool:
        # Most Ollama models support tool calling now, but some don't
        return True

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        import httpx

        # Convert multimodal content to Ollama format (images as base64 in message)
        formatted = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                text_parts = []
                images_b64 = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "image":
                        images_b64.append(block["source"]["data"])
                entry = {"role": msg["role"], "content": " ".join(text_parts)}
                if images_b64:
                    entry["images"] = images_b64
                formatted.append(entry)
            else:
                formatted.append(msg)

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            body["tools"] = [
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

        try:
            resp = httpx.post(
                f"{self._base_url}/api/chat",
                json=body,
                timeout=120.0,
            )
            resp.raise_for_status()
        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Is Ollama running? Start it with: ollama serve"
            )

        data = resp.json()
        message = data.get("message", {})

        tool_calls = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", {}),
                })

        return LLMResponse(
            text=message.get("content", ""),
            tool_calls=tool_calls,
            finish_reason="stop",
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            raw=data,
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
        import httpx

        # Same message formatting as chat()
        formatted = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                text_parts = []
                images_b64 = []
                for block in msg["content"]:
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "image":
                        images_b64.append(block["source"]["data"])
                entry = {"role": msg["role"], "content": " ".join(text_parts)}
                if images_b64:
                    entry["images"] = images_b64
                formatted.append(entry)
            else:
                formatted.append(msg)

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": formatted,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            body["tools"] = [
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

        try:
            with httpx.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=body,
                timeout=120.0,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    message = data.get("message", {})

                    # Text content
                    if message.get("content"):
                        yield StreamEvent(type="text", text=message["content"])

                    # Tool calls (Ollama sends them complete, not incremental)
                    if message.get("tool_calls"):
                        tool_calls = []
                        for tc in message["tool_calls"]:
                            func = tc.get("function", {})
                            tool_calls.append({
                                "id": f"call_{len(tool_calls)}",
                                "name": func.get("name", ""),
                                "arguments": func.get("arguments", {}),
                            })
                        yield StreamEvent(type="tool_calls", tool_calls=tool_calls)

                    if data.get("done"):
                        break

        except httpx.ConnectError:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                "Is Ollama running? Start it with: ollama serve"
            )

        yield StreamEvent(type="done")
