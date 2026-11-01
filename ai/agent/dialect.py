"""The chat-completions wire dialect (IR-727).

Encodes a typed request and decodes a wire response. Any shape it cannot
read completely becomes a MALFORMED turn with no items, never a partial one.
"""

from __future__ import annotations

from typing import Any

from ai.agent.protocol import (
    AgentRequest, ModelTurn, Opaque, Pin, StopReason, Text, ToolCall, ToolGroup, ToolResult, User,
    check_history,
)

FINISH = {
    "stop": StopReason.END, "length": StopReason.LENGTH,
    "tool_calls": StopReason.TOOLS, "content_filter": StopReason.FILTERED,
}


class _Malformed(Exception):
    pass


class ChatCompletions:
    name = "chat-completions-1"
    #: Message fields that carry opaque continuation artifacts.
    opaque_fields = ("reasoning_details",)

    @classmethod
    def encode(cls, request: AgentRequest) -> dict:
        check_history(request)
        messages: list[dict] = [{"role": "system", "content": request.instructions}]
        for entry in request.history:
            if isinstance(entry, User):
                messages.append({"role": "user", "content": entry.text})
            elif isinstance(entry, ToolResult):
                messages.append({"role": "tool", "tool_call_id": entry.call_id, "content": entry.content})
            else:
                messages.append(cls._assistant(entry))
        payload: dict = {"model": request.pin.model, "messages": messages}
        if request.tools:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": t.name, "description": t.description, "parameters": t.parameters,
                }} for t in request.tools
            ]
        return payload

    @staticmethod
    def _assistant(turn: ModelTurn) -> dict:
        message: dict[str, Any] = {"role": "assistant", "content": None}
        if turn.text:
            message["content"] = turn.text
        calls = [c for i in turn.items if isinstance(i, ToolGroup) for c in i.calls]
        if calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in calls
            ]
        for item in turn.items:
            if isinstance(item, Opaque):
                message[item.field] = item.payload
        return message

    @classmethod
    def decode(cls, response: Any, pin: Pin) -> ModelTurn:
        try:
            return cls._decode(response, pin.binding())
        except _Malformed:
            return ModelTurn(items=(), stop=StopReason.MALFORMED)

    @classmethod
    def _decode(cls, response, binding) -> ModelTurn:
        try:
            choice = response["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError):
            raise _Malformed from None
        if not isinstance(message, dict):
            raise _Malformed
        stop = FINISH.get(choice.get("finish_reason"))
        if stop is None:
            raise _Malformed
        items: list = []
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise _Malformed
        if content:
            items.append(Text(content))
        raw_calls = message.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            raise _Malformed
        if raw_calls:
            items.append(ToolGroup(tuple(cls._call(c) for c in raw_calls)))
            ids = [c.id for c in items[-1].calls]
            if len(set(ids)) != len(ids):
                raise _Malformed
        if (stop is StopReason.TOOLS) != bool(raw_calls):
            raise _Malformed
        for name in cls.opaque_fields:
            if message.get(name) is not None:
                items.append(Opaque(binding=binding, field=name, payload=message[name]))
        usage = response.get("usage") or {}
        return ModelTurn(
            items=tuple(items), stop=stop, reasoned=bool(message.get("reasoning")),
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
        )

    @staticmethod
    def _call(raw) -> ToolCall:
        try:
            call_id, function = raw["id"], raw["function"]
            name, arguments = function["name"], function.get("arguments", "{}")
        except (KeyError, TypeError):
            raise _Malformed from None
        if not (isinstance(call_id, str) and call_id and isinstance(name, str) and name
                and isinstance(arguments, str)):
            raise _Malformed
        return ToolCall(call_id, name, arguments)
