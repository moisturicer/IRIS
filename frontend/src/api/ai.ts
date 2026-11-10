import { apiClient } from "./client";
import type {
  AIStatus,
  ConversationSummary,
  ConversationDetail,
  RecordOverviewResponse,
} from "@/types/ai";

/** The reader protocol (IR-595): the server allowlists what it sends back. */
const PUBLIC_CONFIG = { headers: { "X-IRIS-Protocol": "public-1" } } as const;

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

  /**
   * Conversations Django answered before IR-957, read-only: the AI runtime
   * keeps its own. Listed, read and deleted through the owner-scoped API.
   */
  conversations: {
    list: (params?: { record?: number }) =>
      apiClient.get<ConversationSummary[]>("/ai/conversations/", { params }),

    get: (id: number) =>
      apiClient.get<ConversationDetail>(`/ai/conversations/${id}/`, PUBLIC_CONFIG),

    remove: (id: number) => apiClient.delete(`/ai/conversations/${id}/`),
  },
};
