import { apiClient } from "./client";
import { API_BASE } from "@/lib/constants";
import { readSSE, type SSEEvent } from "@/lib/sse";
import { useAuthStore } from "@/store/auth.store";
import type {
  Passage,
  SemanticSearchResult,
  AIAnswer,
  AIStatus,
  ConversationSummary,
  ConversationDetail,
  ResponseStyle,
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
  /** How long and structured the answer should be (IR-332). Server default
   *  is "balanced" when omitted. */
  responseStyle?: ResponseStyle;
}

/**
 * `/ai/ask/stream/` as Server-Sent Events (IR-329). Goes through `fetch`
 * directly, not `apiClient` -- `EventSource` can't carry the auth header,
 * and this bypasses axios's 401-refresh interceptor too (accepted gap: a
 * session that expires mid-stream just surfaces as a stream failure).
 */
async function* streamAsk(
  body: Record<string, unknown>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const token = useAuthStore.getState().accessToken;
  const response = await fetch(`${API_BASE}/ai/ask/stream/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    let detail = "IRIS could not answer right now.";
    try {
      const errorBody = await response.json();
      detail = errorBody.detail ?? detail;
    } catch {
      /* a non-JSON error body -- the generic message stands */
    }
    throw new Error(detail);
  }

  yield* readSSE(response);
}

export const aiApi = {
  /** Whether answers will be generated or retrieval-only, and how many records are indexed. */
  status: () => apiClient.get<AIStatus>("/ai/status/"),

  /** Ranked retrieval over the readable corpus, without synthesis. */
  search: (query: string, topK = 10) =>
    apiClient.post<SemanticSearchResponse>("/ai/search/", { query, top_k: topK }),

  /** Grounded answer plus the records it cites. */
  ask: (question: string, { topK = 5, conversationId, widen, responseStyle }: AskOptions = {}) =>
    apiClient.post<AIAnswer>("/ai/ask/", {
      question,
      top_k: topK,
      conversation_id: conversationId,
      widen,
      response_style: responseStyle,
    }),

  /** The same question, narrated as SSE (IR-326, IR-329) -- see `streamAsk`. */
  askStream: (
    question: string,
    { topK = 5, conversationId, widen, responseStyle }: AskOptions = {},
    signal?: AbortSignal,
  ) =>
    streamAsk(
      {
        question,
        top_k: topK,
        conversation_id: conversationId,
        widen,
        response_style: responseStyle,
      },
      signal,
    ),

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

    remove: (id: number) => apiClient.delete(`/ai/conversations/${id}/`),

    /**
     * The Conversation already scoped to this Record, or a new one if none
     * exists yet — what Paper Chat opens on (IR-298). Kept next to the calls
     * it composes rather than in the component, so the "find one, else start
     * one" decision lives with the data it is about.
     */
    findOrCreateForRecord: async (recordId: number): Promise<{ data: ConversationDetail }> => {
      const { data: existing } = await apiClient.get<ConversationSummary[]>(
        "/ai/conversations/",
        { params: { record: recordId } },
      );
      return existing[0]
        ? apiClient.get<ConversationDetail>(`/ai/conversations/${existing[0].id}/`)
        : apiClient.post<ConversationDetail>("/ai/conversations/", { record: recordId });
    },
  },
};

// NOTE: summarize / embed endpoints are intentionally absent — apps.ai has no
// implementation behind them yet, so calling them would 404. Add them here when
// the services exist.
