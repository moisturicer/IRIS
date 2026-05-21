import { apiClient } from "./client";
import type { SemanticSearchResult, AIAnswer, EmbeddingJobStatus } from "@/types/ai";

interface SemanticSearchResponse {
  results: SemanticSearchResult[];
}

export const aiApi = {
  /** Semantic similarity search -- returns ranked record list */
  semanticSearch: (query: string, topK = 10) =>
    apiClient.post<SemanticSearchResponse>("/ai/search/", { query, top_k: topK }),

  /** Ask a free-form question -- backend does RAG and returns an answer string */
  ask: (question: string) =>
    apiClient.post<AIAnswer>("/ai/ask/", { question }),

  embedOne: (recordId: number) =>
    apiClient.post<EmbeddingJobStatus>(`/ai/embed/${recordId}/`),

  embedAll: () =>
    apiClient.post("/ai/embed/all/"),

  jobs: () =>
    apiClient.get<EmbeddingJobStatus[]>("/ai/embed/jobs/"),
};
