"""One contextualized Voyage request, with no retries or internal batching."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]
    input_tokens: int | None


class VoyageContextEmbeddings:
    def __init__(self, api_key: str, *, model: str, dimensions: int):
        if not api_key.strip() or model != "voyage-context-4" or dimensions != 1024:
            raise ValueError("a key and the supported model and dimensions are required")
        self._key = api_key.strip()
        self.model, self.dimensions = model, dimensions
        self.account = hashlib.sha256(self._key.encode()).hexdigest()[:32]

    async def embed(self, texts, *, input_type):
        if input_type not in ("document", "query") or not texts:
            raise ValueError("nonempty document or query input required")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.voyageai.com/v1/contextualizedembeddings",
                headers={"Authorization": f"Bearer {self._key}"},
                json={
                    "model": self.model,
                    "inputs": [list(texts)],
                    "input_type": input_type,
                    "output_dimension": self.dimensions,
                },
            )
            response.raise_for_status()
            body = response.json()
        groups = body.get("data", [])
        if len(groups) != 1 or len(groups[0].get("data", [])) != len(texts):
            raise ValueError("incomplete embedding response")
        usage = body.get("usage", {}).get("total_tokens")
        if type(usage) is not int or usage < 0:
            usage = None
        return Embeddings([item["embedding"] for item in groups[0]["data"]], usage)
