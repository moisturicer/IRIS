/**
 * Chat-screen message shape, shared by Ask IRIS and Paper Chat (IR-298).
 *
 * A thin view over the backend's Conversation/Turn wire shapes
 * (`types/ai.ts`) rather than a second source of truth: a live answer maps
 * straight onto one of these, and so does a replayed Turn, which is what
 * lets both surfaces render through the same `ChatMessageBubble`.
 */
import type { ChatCitation, SemanticSearchResult } from "./ai";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id:         string;
  role:       ChatRole;
  content:    string;
  /**
   * The Passages this reply cited (IR-284). A live answer's citations carry
   * the quote and the record's title; a replayed Turn's carry only the
   * pointer (record, chunk, page) until IR-299 re-resolves the text.
   */
  citations?: ChatCitation[];
  /**
   * The Record cards for those Passages, as the answer returned them.
   *
   * Stored with the reply rather than held in screen state: state reset to
   * `[]` on every conversation switch and did not survive a reload, so the
   * sources panel showed passages whose authors had gone missing — or, worse,
   * cards left over from the previous conversation.
   */
  sources?:   SemanticSearchResult[];
  /** True when retrieval fell back to keyword matching for this reply. */
  degraded?:  boolean;
  /**
   * True when this reply left its Conversation's Record scope because the
   * reader asked to search all papers (IR-298, ADR-026 §9). Undefined for a
   * user message, and for an assistant message in an unscoped Conversation.
   */
  widened?:   boolean;
  /**
   * True when the stream that produced this reply never reached its
   * terminal event — the connection dropped, the vendor timed out, the
   * server restarted (IR-328) — so `content` is whatever text arrived
   * before the cutoff, not the model's complete answer (IR-329).
   */
  partial?:   boolean;
  createdAt:  string;
}
