import type { ChatMessage, Conversation } from "@/types/chat";

const STORAGE_KEY = "iris_rag_conversations";

function readAll(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Conversation[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeAll(conversations: Conversation[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
}

export function listConversations(): Conversation[] {
  return readAll().sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

export function getConversation(id: string): Conversation | undefined {
  return readAll().find((c) => c.id === id);
}

export function createConversation(): Conversation {
  const now = new Date().toISOString();
  const conversation: Conversation = {
    id:        crypto.randomUUID(),
    title:     "New conversation",
    messages:  [],
    createdAt: now,
    updatedAt: now,
  };
  const all = readAll();
  writeAll([conversation, ...all]);
  return conversation;
}

export function saveConversation(conversation: Conversation): void {
  const all = readAll();
  const idx = all.findIndex((c) => c.id === conversation.id);
  const next = { ...conversation, updatedAt: new Date().toISOString() };
  if (idx >= 0) {
    all[idx] = next;
  } else {
    all.unshift(next);
  }
  writeAll(all);
}

export function deleteConversation(id: string): void {
  writeAll(readAll().filter((c) => c.id !== id));
}

export function titleFromFirstMessage(content: string): string {
  const line = content.trim().split(/\n/)[0] ?? "New conversation";
  return line.length > 48 ? `${line.slice(0, 45)}…` : line;
}

/** Build a single prompt including prior turns for the RAG ask endpoint. */
export function buildRagQuestion(messages: ChatMessage[]): string {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "user") return "";
  if (messages.length <= 1) return last.content;

  const history = messages
    .slice(0, -1)
    .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
    .join("\n\n");

  return `Previous conversation:\n${history}\n\nCurrent question:\n${last.content}`;
}
