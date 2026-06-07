from typing import List
from .interfaces import LLMProvider, EmbeddingProvider
from ai.core.config import settings
import httpx

class LocalLLMProvider(LLMProvider):
    def __init__(self):
        self.url = settings.LOCAL_LLM_URL
        self.model = settings.LLM_MODEL

    async def generate_response(self, prompt: str, context: str = "") -> str:
        # Placeholder for local model (e.g. Ollama API)
        # Using httpx to hit self.url + "/api/generate"
        full_prompt = f"Context: {context}\n\nQuestion: {prompt}" if context else prompt
        
        async with httpx.AsyncClient() as client:
            # Example payload for Ollama
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False
            }
            # For now, just return a mock so we don't break if not running
            # response = await client.post(f"{self.url}/api/generate", json=payload)
            # return response.json().get("response", "")
            return f"Mock response from LocalLLMProvider for prompt: {prompt}"

class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        self.url = settings.LOCAL_LLM_URL
        self.model = settings.EMBEDDING_MODEL

    async def generate_embedding(self, text: str) -> List[float]:
        # Placeholder for local embedding
        # Example: return [0.0] * settings.AI_EMBEDDING_DIMENSIONS
        return [0.0] * 1536 # You should ideally inject the dimension size from config
