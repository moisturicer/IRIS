/** Local chat session types (FR-M3-01 — persisted in browser until backend conversations exist). */
import type { Citation, SemanticSearchResult } from "./ai";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id:         string;
  role:       ChatRole;
  content:    string;
  /**
   * The Passages this reply cited (IR-284). Previously record ids; a
   * conversation saved under that shape is normalised away on read rather
   * than migrated, since nothing can recover a quote from an id.
   */
  citations?: Citation[];
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
  createdAt:  string;
}

export interface Conversation {
  id:         string;
  title:      string;
  messages:   ChatMessage[];
  createdAt:  string;
  updatedAt:  string;
}
