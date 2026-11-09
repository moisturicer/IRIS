import hashlib
import json

import openai

import httpx
from typing import List, Optional
from ai.admission import scope
from ai.admission.errors import NOT_ADMITTED, AdmissionDenied
from ai.agent.dialect import ChatCompletions
from ai.domain.ports import (
    LLMProvider, EmbeddingProvider, ProviderRejected, TransientProviderError, UnsupportedCapability,
)
from ai.infrastructure import agent_config
from ai.infrastructure.settings import settings
from ai.runs import stream

#: Statuses another attempt may not meet; any other non-2xx is a refusal.
TRANSIENT_STATUSES = frozenset({408, 409, 429})

class OpenAILLMProvider(LLMProvider):
    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.LLM_MODEL

    async def generate_response(self, prompt: str, context: str = "") -> str:
        messages = [
            {"role": "system", "content": "You are a helpful assistant for the IRIS research repository. Answer questions based on the provided context. If the context does not contain the answer, say you don't know."}
        ]

        if context:
            messages.append({"role": "system", "content": f"Context:\n{context}"})

        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.0
        )
        return response.choices[0].message.content


class OpenAICompatibleAgentProvider(LLMProvider):
    """AGENT turns from the configured chat-completions endpoint (IR-860).

    Sends exactly what the dialect encodes and decodes exactly what comes
    back. Plain `httpx`, not the vendor SDK: nothing retries out of sight and
    no library logs the payload. It refuses to send outside an attempt
    `AdmittedAgentProvider` has admitted. Errors carry a status, never content.
    """

    adapter = "openai-compatible"
    #: Bills per attempt: reached only through admission (IR-725).
    paid = True
    dialect = ChatCompletions

    def __init__(self, config: agent_config.AgentProviderConfig, *,
                 http_client: Optional[httpx.AsyncClient] = None):
        self.config = config
        #: Injected by tests; otherwise one client per send, bounded by admission's deadline.
        self._http_client = http_client

    @classmethod
    def from_settings(cls, values=settings, **options) -> "OpenAICompatibleAgentProvider":
        """Validates the declaration first: `NotConfigured` names what is wrong."""
        return cls(agent_config.read(values), **options)

    def accepts(self, pin) -> bool:
        return (
            pin.adapter == self.adapter and pin.endpoint == self.config.endpoint
            and pin.model in self.config.models and pin.dialect == self.dialect.name
            and pin.data_policy == self.config.data_policy and set(pin.requires) <= self.config.capabilities
        )

    def capacity(self, pin):
        return self.config.capacities.get(pin.model) if self.accepts(pin) else None

    @property
    def routing(self):
        return self.config.routing

    def encode(self, request):
        payload = self.dialect.encode(request)
        if self.config.routing is not None:
            payload["provider"] = self.config.routing
        return payload

    @property
    def account(self) -> str:
        """A digest naming the vendor account: endpoint and key, never the key itself."""
        return hashlib.sha256(f"{self.config.endpoint}\0{self.config.api_key}".encode()).hexdigest()[:32]

    async def generate_response(self, prompt: str, context: str = "") -> str:
        raise UnsupportedCapability("generate_response")

    async def converse(self, request):
        if not scope.sending():
            raise AdmissionDenied(NOT_ADMITTED)
        if not self.accepts(request.pin):
            raise UnsupportedCapability("pin")
        payload = self.encode(request)
        sink = stream.active()
        if sink is not None:
            body = await self._stream(payload, sink)
            return self.dialect.decode(body, request.pin)
        response = await self._post(payload)
        try:
            body = response.json()
        except ValueError:
            body = None
        return self.dialect.decode(body, request.pin)

    async def _stream(self, payload: dict, sink) -> Optional[dict]:
        """The same response body as a plain send, assembled from the stream; text pieces go to `sink` as they arrive."""
        url = f"{self.config.endpoint}/chat/completions"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        body = {**payload, "stream": True, "stream_options": {"include_usage": True}}
        message: dict = {"role": "assistant", "content": ""}
        calls: dict[int, dict] = {}
        finish, usage, extra = None, None, {}

        async def read(client):
            nonlocal finish, usage
            async with client.stream("POST", url, json=body, headers=headers) as response:
                status = response.status_code
                if status in TRANSIENT_STATUSES or status >= 500:
                    raise TransientProviderError(f"status {status}")
                if not 200 <= status < 300:
                    raise ProviderRejected(f"status {status}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    if chunk.get("error"):
                        raise TransientProviderError("stream error")
                    usage = chunk.get("usage") or usage
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            message["content"] += delta["content"]
                            await sink.text(delta["content"])
                        if delta.get("reasoning"):
                            message["reasoning"] = (message.get("reasoning") or "") + delta["reasoning"]
                        for name in self.dialect.opaque_fields:
                            if isinstance(delta.get(name), list):
                                extra.setdefault(name, []).extend(delta[name])
                        for call in delta.get("tool_calls") or []:
                            slot = calls.setdefault(call.get("index", len(calls)),
                                                    {"type": "function", "function": {"name": "", "arguments": ""}})
                            if call.get("id"):
                                slot["id"] = call["id"]
                            function = call.get("function") or {}
                            if function.get("name"):
                                slot["function"]["name"] += function["name"]
                            if function.get("arguments"):
                                slot["function"]["arguments"] += function["arguments"]
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]

        try:
            if self._http_client is not None:
                await read(self._http_client)
            else:
                async with httpx.AsyncClient(timeout=None) as client:
                    await read(client)
        except httpx.HTTPError as failed:
            raise TransientProviderError(type(failed).__name__) from None
        if finish is None:
            return None
        if calls:
            message["tool_calls"] = [calls[i] for i in sorted(calls)]
        if not message["content"]:
            message["content"] = None
        message.update(extra)
        return {"choices": [{"message": message, "finish_reason": finish}], "usage": usage or {}}

    async def _post(self, payload: dict) -> httpx.Response:
        url = f"{self.config.endpoint}/chat/completions"
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        try:
            if self._http_client is not None:
                response = await self._http_client.post(url, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=None) as client:
                    response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as failed:
            raise TransientProviderError(type(failed).__name__) from None
        status = response.status_code
        if status in TRANSIENT_STATUSES or status >= 500:
            raise TransientProviderError(f"status {status}")
        if not 200 <= status < 300:
            raise ProviderRejected(f"status {status}")
        return response


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI is not asymmetric: the same model embeds a document and a
    query the same way. Both port methods are implemented, and both route
    through the same batched call — the two-method shape exists for the
    port's contract, not because this particular provider needs it."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.EMBEDDING_MODEL

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        response = await self.client.embeddings.create(input=texts, model=self.model)
        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> List[float]:
        response = await self.client.embeddings.create(input=[text], model=self.model)
        return response.data[0].embedding
