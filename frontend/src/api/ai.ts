import { apiClient } from "./client";
import type {
  Passage,
  SemanticSearchResult,
  AIAnswer,
  AIStatus,
  ConversationSummary,
  ConversationDetail,
} from "@/types/ai";

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

interface AskOptions {
  topK?: number;
  /** Appends the question and its answer to this Conversation as a Turn (IR-295). */
  conversationId?: number;
  /**
   * Search every paper instead of just the Conversation's Record, for this
   * question only (IR-298, ADR-026 §9). Has no effect on an unscoped
   * Conversation or a one-off question with no `conversationId`.
   */
  widen?: boolean;
}

export const aiApi = {
  /** Whether answers will be generated or retrieval-only, and how many records are indexed. */
  status: () => apiClient.get<AIStatus>("/ai/status/"),

  /** Ranked retrieval over the readable corpus, without synthesis. */
  search: (query: string, topK = 10) =>
    apiClient.post<SemanticSearchResponse>("/ai/search/", { query, top_k: topK }),

  /** Grounded answer plus the records it cites. */
  ask: (question: string, { topK = 5, conversationId, widen }: AskOptions = {}) =>
    apiClient.post<AIAnswer>("/ai/ask/", {
      question,
      top_k: topK,
      conversation_id: conversationId,
      widen,
    }),

  conversations: {
    /** The caller's own Conversations, most recent first — optionally the
     * one(s) scoped to a single Record, for Paper Chat to continue (IR-298). */
    list: (params?: { record?: number }) =>
      apiClient.get<ConversationSummary[]>("/ai/conversations/", { params }),

    /** Start a Conversation, optionally scoped to a Record. */
    create: (body: { record?: number; title?: string } = {}) =>
      apiClient.post<ConversationDetail>("/ai/conversations/", body),

    get: (id: number) =>
      apiClient.get<ConversationDetail>(`/ai/conversations/${id}/`),

    rename: (id: number, title: string) =>
      apiClient.patch<ConversationDetail>(`/ai/conversations/${id}/`, { title }),

    remove: (id: number) => apiClient.delete(`/ai/conversations/${id}/`),
  },
};

// NOTE: summarize / embed endpoints are intentionally absent — apps.ai has no
// implementation behind them yet, so calling them would 404. Add them here when
// the services exist.
