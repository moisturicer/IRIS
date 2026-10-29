import { apiClient, refreshSession } from "./client";
import { IDLE_HEADER, idleSeconds, markReported } from "@/lib/activity";
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
  RecordOverviewResponse,
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
  /** Reuse on transport retry; a new question gets a new identity. */
  requestId?: string;
  comparisonRecordIds?: number[];
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

/** The reader protocol (IR-595): the server allowlists what it sends back. */
const PUBLIC_PROTOCOL = { "X-IRIS-Protocol": "public-1" } as const;
const PUBLIC_CONFIG = { headers: PUBLIC_PROTOCOL };

async function checkComparisonLimit(recordIds?: number[]): Promise<void> {
  if (recordIds === undefined) return;
  if (recordIds.length < 2) throw new Error("Choose at least 2 papers to compare.");
  if (recordIds.some((id) => !Number.isInteger(id) || id < 1) || new Set(recordIds).size !== recordIds.length) {
    throw new Error("Choose distinct valid papers to compare.");
  }
  let limit = 6;
  try {
    const { data } = await apiClient.get<AIStatus>("/ai/status/");
    const configured = data.comparison_max_records;
    if (configured !== undefined && Number.isInteger(configured) && configured >= 2) limit = configured;
  } catch {
    // The server still enforces its configured limit when status is unavailable.
  }
  if (recordIds.length > limit) throw new Error(`Compare at most ${limit} papers at a time.`);
}

/**
 * `/ai/ask/stream/` as Server-Sent Events (IR-329). Goes through `fetch`
 * directly, not `apiClient` -- `EventSource` can't carry the auth header --
 * so `openStream` does what the axios interceptors would (IR-634).
 */
async function* streamAsk(
  body: Record<string, unknown>,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  await checkComparisonLimit(body.comparison_record_ids as number[] | undefined);
  yield* openStream(`${API_BASE}/ai/ask/stream/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...PUBLIC_PROTOCOL },
    body: JSON.stringify(body),
    signal,
  });
}

/** The same event stream, for one already-submitted queued run (IR-544). */
async function* resumeAskRun(
  runId: string,
  after: number,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  yield* openStream(
    `${API_BASE}/ai/ask/runs/${encodeURIComponent(runId)}/stream/?after=${after}`,
    { ...PUBLIC_CONFIG, method: "GET", signal },
  );
}

/**
 * What `apiClient`'s interceptors do, for `fetch`: report idleness, so a
 * stream does not keep an idle session alive, and on a 401 refresh once and
 * retry (IR-166, IR-634). A 401 is refused at authentication, before anything
 * runs, so sending the request again is safe. When the refresh fails the user
 * has been logged out and redirected, and the 401 surfaces as a stream error.
 */
async function* openStream(url: string, init: RequestInit): AsyncGenerator<SSEEvent> {
  let response = await send(url, init, useAuthStore.getState().accessToken);
  if (response.status === 401) {
    const access = await refreshSession();
    if (access) response = await send(url, init, access);
  }

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

function send(url: string, init: RequestInit, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
    [IDLE_HEADER]: String(idleSeconds()),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  markReported();
  return fetch(url, { ...init, headers });
}

/**
 * Start a Conversation. The server answers with the summary shape (no
 * `turns`); a new conversation has no Turns and no run, so that is filled in
 * here, once, rather than read as `undefined` by each caller (IR-548).
 */
async function createConversation(
  body: { record?: number; title?: string; reuse_default?: boolean } = {},
): Promise<{ data: ConversationDetail }> {
  const { data } = await apiClient.post<ConversationDetail>("/ai/conversations/", body, PUBLIC_CONFIG);
  return { data: { ...data, turns: data.turns ?? [], latest_run: data.latest_run ?? null } };
}

export const aiApi = {
  /** Whether answers will be generated or retrieval-only, and how many records are indexed. */
  status: () => apiClient.get<AIStatus>("/ai/status/"),

  /**
   * A record's AI Overview, generated once and cached server-side (IR-334).
   * Replaces firing `ask()` from the paper view on every mount.
   */
  overview: (recordId: number, retry = false) =>
    apiClient.get<RecordOverviewResponse>(`/ai/records/${recordId}/overview/`, {
      params: retry ? { retry: true } : undefined,
    }),

  /** Ranked retrieval over the readable corpus, without synthesis. */
  search: (query: string, topK = 10) =>
    apiClient.post<SemanticSearchResponse>("/ai/search/", { query, top_k: topK }),

  /** Grounded answer plus the records it cites. */
  ask: (question: string, { topK = 5, conversationId, widen, comparisonRecordIds, requestId = crypto.randomUUID() }: AskOptions = {}) => {
    const send = () => apiClient.post<AIAnswer>("/ai/ask/", {
      question,
      top_k: topK,
      conversation_id: conversationId,
      ...(conversationId ? { request_id: requestId } : {}),
      widen,
      ...(comparisonRecordIds !== undefined ? { comparison_record_ids: comparisonRecordIds } : {}),
    }, PUBLIC_CONFIG);
    return comparisonRecordIds === undefined ? send() : checkComparisonLimit(comparisonRecordIds).then(send);
  },

  /** The same question, narrated as SSE (IR-326, IR-329) -- see `streamAsk`. */
  askStream: (
    question: string,
    { topK = 5, conversationId, widen, comparisonRecordIds, requestId = crypto.randomUUID() }: AskOptions = {},
    signal?: AbortSignal,
  ) =>
    streamAsk(
      { question, top_k: topK, conversation_id: conversationId, widen, ...(conversationId ? { request_id: requestId } : {}), ...(comparisonRecordIds !== undefined ? { comparison_record_ids: comparisonRecordIds } : {}) },
      signal,
    ),

  /** Reconnect to a queued run after event `after` (IR-544) -- see `resumeAskRun`. */
  resumeAskRun,

  /** Stop the reader's own queued run (IR-548). 409 once it has already ended. */
  cancelRun: (runId: string) =>
    apiClient.post<{ run_id: string; state: string }>(
      `/ai/ask/runs/${encodeURIComponent(runId)}/cancel/`,
    ),

  /**
   * Ask a run that ended without its answer again, as a new linked run
   * (IR-548). Repeating it returns the same retry, never a second one.
   */
  retryRun: (runId: string) =>
    apiClient.post<{ run_id: string; retry_of: string; state: string }>(
      `/ai/ask/runs/${encodeURIComponent(runId)}/retry/`,
    ),

  conversations: {
    /** The caller's own Conversations, most recent first — optionally the
     * one(s) scoped to a single Record, for Paper Chat to continue (IR-298). */
    list: (params?: { record?: number }) =>
      apiClient.get<ConversationSummary[]>("/ai/conversations/", { params }),

    /** Start a Conversation, optionally scoped to a Record. */
    create: createConversation,

    get: (id: number) =>
      apiClient.get<ConversationDetail>(`/ai/conversations/${id}/`, PUBLIC_CONFIG),

    remove: (id: number) => apiClient.delete(`/ai/conversations/${id}/`),

    /**
     * The Conversation already scoped to this Record, or null -- what Paper
     * Chat opens on (IR-298). Opening never starts one (IR-569): Paper Chat
     * creates it with the first question.
     */
    findForRecord: async (recordId: number): Promise<ConversationDetail | null> => {
      const { data: existing } = await apiClient.get<ConversationSummary[]>(
        "/ai/conversations/",
        { params: { record: recordId, default: true } },
      );
      if (!existing[0]) return null;
      const { data } = await apiClient.get<ConversationDetail>(
        `/ai/conversations/${existing[0].id}/`,
        PUBLIC_CONFIG,
      );
      return data;
    },
  },
};

// NOTE: summarize / embed endpoints are intentionally absent — apps.ai has no
// implementation behind them yet, so calling them would 404. Add them here when
// the services exist.
