import { apiClient } from "./client";
import type { Passage, SemanticSearchResult, AIAnswer, AIStatus } from "@/types/ai";

interface SemanticSearchResponse {
  /** Ranked Passages — the same shape an answer cites (IR-284). */
  results:  Passage[];
  count:    number;
  /** The Record cards those Passages came from, so no card needs a second fetch. */
  sources:  SemanticSearchResult[];
  /** True when the vendor was out and these came from keyword matching. */
  degraded: boolean;
  message:  string | null;
}

export const aiApi = {
  /** Whether answers will be generated or retrieval-only, and how many records are indexed. */
  status: () => apiClient.get<AIStatus>("/ai/status/"),

  /** Ranked retrieval over the readable corpus, without synthesis. */
  search: (query: string, topK = 10) =>
    apiClient.post<SemanticSearchResponse>("/ai/search/", { query, top_k: topK }),

  /** Grounded answer plus the records it cites. */
  ask: (question: string, topK = 5) =>
    apiClient.post<AIAnswer>("/ai/ask/", { question, top_k: topK }),
};

// NOTE: summarize / embed endpoints are intentionally absent — apps.ai has no
// implementation behind them yet, so calling them would 404. Add them here when
// the services exist.
