/** Local chat session types (FR-M3-01 — persisted in browser until backend conversations exist). */

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id:         string;
  role:       ChatRole;
  content:    string;
  citations?: number[];
  createdAt:  string;
}

export interface Conversation {
  id:         string;
  title:      string;
  messages:   ChatMessage[];
  createdAt:  string;
  updatedAt:  string;
}
