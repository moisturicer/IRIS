import openai
from typing import List
from ai.domain.ports import LLMProvider, EmbeddingProvider
from ai.infrastructure.settings import settings

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
