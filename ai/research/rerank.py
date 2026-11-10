"""One Voyage rerank request, with no retries (IR-886).

Called only by `ResearchTools.hybrid_search`, after admission.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx

ENDPOINT = "https://api.voyageai.com/v1"


@dataclass(frozen=True)
class Ranked:
    #: Input positions, best first.
    order: list[int]
    input_tokens: int | None


class VoyageReranker:
    endpoint = ENDPOINT
    adapter = "voyage"

    def __init__(self, api_key: str, *, model: str):
        if not api_key.strip() or not model.strip():
            raise ValueError("a Voyage key and a rerank model are required")
        self._key = api_key.strip()
        self.model = model.strip()
        self.account = hashlib.sha256(self._key.encode()).hexdigest()[:32]

    async def rerank(self, query: str, texts: list[str]) -> Ranked:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ENDPOINT}/rerank", headers={"Authorization": f"Bearer {self._key}"},
                json={"query": query, "documents": list(texts), "model": self.model, "top_k": len(texts)},
            )
            response.raise_for_status()
            body = response.json()
        order = [item["index"] for item in body.get("data", [])]
        usage = body.get("usage", {}).get("total_tokens")
        return Ranked(order, usage if type(usage) is int and usage >= 0 else None)
