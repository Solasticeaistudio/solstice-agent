"""
Gemini Provider
===============
Gemini 2.5 Pro, Flash, etc. With native Google Search grounding.
Requires: pip install google-genai
"""

import logging
from typing import Generator, List, Dict, Any, Optional

from .base import BaseLLMProvider, LLMResponse, StreamEvent

log = logging.getLogger("solstice.provider.gemini")


def _sanitize_params_for_gemini(params):
    """Recursively convert enum values to strings (Gemini SDK requirement)."""
    if not isinstance(params, dict):
        return params
    import copy
    result = copy.deepcopy(params)
    for key, value in result.items():
        if key == "enum" and isinstance(value, list):
            result[key] = [str(v) for v in value]
        elif isinstance(value, dict):
            result[key] = _sanitize_params_for_gemini(value)
    return result


class GeminiProvider(BaseLLMProvider):

    def __init__(self, api_key: str = "", model: str = "gemini-2.5-flash", **kwargs):
        super().__init__(api_key, model, **kwargs)
        self._search_grounding = kwargs.get("search_grounding", False)

    def name(self) -> str:
        return f"Gemini ({self.model})"

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Gemini provider requires: pip install google-genai")

        client = genai.Client(api_key=self.api_key)

        # Convert messages to Gemini format (with multimodal support)
        system_text = ""
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                content = msg["content"]
                system_text += (content if isinstance(content, str) else str(content)) + "\n"
            elif msg["role"] in ("user", "assistant"):
                role = "user" if msg["role"] == "user" else "model"
                content = msg["content"]
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if block.get("type") == "text":
                            parts.append(types.Part.from_text(text=block["text"]))
                        elif block.get("type") == "image":
                            import base64 as b64
                            src = block.get("source", {})
                            img_bytes = b64.standard_b64decode(src["data"])
                            parts.append(types.Part.from_bytes(
                                data=img_bytes,
                                mime_type=src["media_type"],
                            ))
                        else:
                            parts.append(types.Part.from_text(text=str(block)))
                    contents.append(types.Content(role=role, parts=parts))
                else:
                    contents.append(types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content if isinstance(content, str) else str(content))],
                    ))

        # Build tool declarations
        gemini_tools = []
        if tools:
            declarations = []
            for t in tools:
                declarations.append(types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=_sanitize_params_for_gemini(t.get("parameters")),
                ))
            gemini_tools.append(types.Tool(function_declarations=declarations))

        if self._search_grounding:
            gemini_tools.append(types.Tool(google_search=types.GoogleSearch()))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=gemini_tools or None,
        )
        if system_text.strip():
            config.system_instruction = system_text.strip()

        response = client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        text = ""
        tool_calls = []

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text += part.text
                elif part.function_call:
                    tool_calls.append({
                        "id": f"call_{len(tool_calls)}",
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args) if part.function_call.args else {},
                    })

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            finish_reason="stop",
            usage={},
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
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Gemini provider requires: pip install google-genai")

        client = genai.Client(api_key=self.api_key)

        # Same message formatting as chat()
        system_text = ""
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                content = msg["content"]
                system_text += (content if isinstance(content, str) else str(content)) + "\n"
            elif msg["role"] in ("user", "assistant"):
                role = "user" if msg["role"] == "user" else "model"
                content = msg["content"]
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if block.get("type") == "text":
                            parts.append(types.Part.from_text(text=block["text"]))
                        elif block.get("type") == "image":
                            import base64 as b64
                            src = block.get("source", {})
                            img_bytes = b64.standard_b64decode(src["data"])
                            parts.append(types.Part.from_bytes(
                                data=img_bytes,
                                mime_type=src["media_type"],
                            ))
                        else:
                            parts.append(types.Part.from_text(text=str(block)))
                    contents.append(types.Content(role=role, parts=parts))
                else:
                    contents.append(types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=content if isinstance(content, str) else str(content))],
                    ))

        # Build tool declarations
        gemini_tools = []
        if tools:
            declarations = []
            for t in tools:
                declarations.append(types.FunctionDeclaration(
                    name=t["name"],
                    description=t.get("description", ""),
                    parameters=_sanitize_params_for_gemini(t.get("parameters")),
                ))
            gemini_tools.append(types.Tool(function_declarations=declarations))

        if self._search_grounding:
            gemini_tools.append(types.Tool(google_search=types.GoogleSearch()))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=gemini_tools or None,
        )
        if system_text.strip():
            config.system_instruction = system_text.strip()

        # Gemini streaming
        tool_calls = []
        for chunk in client.models.generate_content_stream(
            model=self.model,
            contents=contents,
            config=config,
        ):
            if not chunk.candidates:
                continue
            for part in chunk.candidates[0].content.parts:
                if part.text:
                    yield StreamEvent(type="text", text=part.text)
                elif part.function_call:
                    tool_calls.append({
                        "id": f"call_{len(tool_calls)}",
                        "name": part.function_call.name,
                        "arguments": dict(part.function_call.args) if part.function_call.args else {},
                    })

        if tool_calls:
            yield StreamEvent(type="tool_calls", tool_calls=tool_calls)

        yield StreamEvent(type="done")
