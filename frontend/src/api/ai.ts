import { apiClient } from "./client";
import type { SemanticSearchResult, AIAnswer, EmbeddingJobStatus } from "@/types/ai";

interface SemanticSearchResponse {
  answer?:  string;
  sources?: SemanticSearchResult[];
  /** Legacy shape if backend adds ranked results */
  results?: SemanticSearchResult[];
}

interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

interface RecordSummary {
  objectives:   string;
  methodology:  string;
  findings:     string;
  conclusion:   string;
}

interface SummarizeResponse {
  summary: RecordSummary;
}

export const aiApi = {
  /** Semantic similarity search -- returns ranked record list */
  semanticSearch: (query: string, topK = 10) =>
    apiClient.post<SemanticSearchResponse>("/ai/search/", { query, top_k: topK }),

  /** Ask a free-form question with optional multi-turn history for conversational context. */
  ask: (question: string, history?: ConversationTurn[]) =>
    apiClient.post<AIAnswer>("/ai/ask/", { question, ...(history && { history }) }),

  /** Generate a four-part structured summary of a record's extracted PDF text via GPT-4.1-mini. */
  summarize: (recordId: number) =>
    apiClient.post<SummarizeResponse>(`/ai/summarize/${recordId}/`),

  embedRecord: (recordId: number) =>
    apiClient.post<EmbeddingJobStatus>(`/ai/embed/${recordId}/`),

  embedAll: () =>
    apiClient.post("/ai/embed/all/"),

  embeddingJobs: () =>
    apiClient.get<EmbeddingJobStatus[]>("/ai/embed/jobs/"),
};
