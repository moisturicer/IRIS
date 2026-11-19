import { useCallback, useEffect, useRef, useState } from "react";
import type { ReaderConversationSummary, runtimeReader } from "@/api/runtimeReader";

const DEBOUNCE_MS = 250;

/** The reader's past Conversations: a first page, older pages on request, and a search (IR-1161). */
export function useConversationHistory(api: ReturnType<typeof runtimeReader>, activeId?: string) {
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [conversations, setConversations] = useState<ReaderConversationSummary[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [loadingMore, setLoadingMore] = useState(false);
  const request = useRef(0);
  const titles = useRef(new Map<string, string>());
  const shown = useRef({ ready: false, ids: new Set<string>() });
  shown.current = { ready: state === "ready", ids: new Set(conversations.map(c => c.id)) };

  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  /** Reloads the first page of the current search; the last request to start is the one shown. */
  const refresh = useCallback(async () => {
    const mine = ++request.current;
    try {
      const page = await api.list({ q: query });
      if (mine !== request.current) return;
      page.conversations.forEach(c => titles.current.set(c.id, c.title));
      setConversations(page.conversations); setNext(page.next); setState("ready");
    } catch {
      // The list is a convenience; the reader still works.
      if (mine === request.current) setState("error");
    }
  }, [api, query]);

  useEffect(() => { setState("loading"); void refresh(); }, [refresh]);

  // A Conversation not yet listed (a new one) reloads; opening a listed one keeps the pages loaded.
  useEffect(() => {
    if (activeId && shown.current.ready && !shown.current.ids.has(activeId)) void refresh();
  }, [activeId, refresh]);

  const loadMore = useCallback(async () => {
    if (!next || loadingMore) return;
    const mine = request.current;
    setLoadingMore(true);
    try {
      const page = await api.list({ q: query, before: next });
      if (mine !== request.current) return;
      page.conversations.forEach(c => titles.current.set(c.id, c.title));
      setConversations(all => [...all, ...page.conversations]); setNext(page.next);
    } catch {
      if (mine === request.current) setState("error");
    } finally { setLoadingMore(false); }
  }, [api, query, next, loadingMore]);

  return {
    conversations, setConversations, refresh, loadMore,
    /** A title seen on any page, so the open Conversation keeps its name while a search hides it. */
    titleOf: (id?: string) => (id ? titles.current.get(id) : undefined),
    /** Shows a title the reader just chose (IR-1160) wherever the Conversation is listed. */
    retitle: useCallback((id: string, title: string) => {
      titles.current.set(id, title);
      setConversations(all => all.map(c => (c.id === id ? { ...c, title } : c)));
    }, []),
    search: { text, onText: setText, query, state, hasMore: next !== null, loadingMore, onMore: () => void loadMore() },
  };
}
