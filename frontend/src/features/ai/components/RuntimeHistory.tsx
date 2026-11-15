import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { runtimeReader, type ConversationPage } from "@/api/runtimeReader";
import { formatDate } from "@/lib/utils";

type Entry = ConversationPage["conversations"][number];

const DEBOUNCE_MS = 250;

interface Props {
  /** The open Conversation, marked in the list; a new one reloads the list. */
  activeId?: string;
}

/** The reader's past Conversations with a search box and paging (IR-1161). */
export function RuntimeHistory({ activeId }: Props) {
  const api = useMemo(() => runtimeReader(), []);
  const searchId = useId();
  const [text, setText] = useState("");
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [more, setMore] = useState(false);
  const request = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  useEffect(() => {
    const mine = ++request.current;
    setState("loading");
    api.list({ q: query }).then(page => {
      if (mine !== request.current) return;
      setEntries(page.conversations); setNext(page.next); setState("ready");
    }).catch(() => { if (mine === request.current) setState("error"); });
  }, [api, query, activeId]);

  const loadMore = async () => {
    if (!next || more) return;
    const mine = request.current;
    setMore(true);
    try {
      const page = await api.list({ q: query, before: next });
      if (mine !== request.current) return;
      setEntries(current => [...current, ...page.conversations]); setNext(page.next);
    } catch {
      if (mine === request.current) setState("error");
    } finally { setMore(false); }
  };

  return <section aria-label="Chat history" className="flex min-h-0 flex-col">
    <div className="px-3 py-3">
      <label htmlFor={searchId} className="sr-only">Search your past conversations</label>
      <input id={searchId} type="search" value={text} onChange={e => setText(e.target.value)}
        placeholder="Search past conversations" autoComplete="off" maxLength={200}
        className="min-h-11 w-full rounded-full border border-stone-200 bg-stone-50 px-4 text-sm text-stone-900 placeholder:text-stone-500 focus-visible:outline-brand" />
    </div>
    <div role="status" aria-live="polite" className="px-4 text-xs text-stone-500">
      {state === "loading" ? "Loading…" : state === "ready" && query
        ? `${entries.length}${next ? "+" : ""} ${entries.length === 1 && !next ? "conversation matches" : "conversations match"}` : ""}
    </div>
    {state === "error" && <p role="alert" className="px-4 py-3 text-sm text-stone-700">Could not load your conversations. Try again.</p>}
    {state === "ready" && entries.length === 0 && <p className="px-4 py-6 text-sm text-stone-500">
      {query ? `No conversations match “${query}”.` : "Your past chats will appear here."}</p>}
    {entries.length > 0 && <nav aria-label="Past conversations" className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
      <ul className="space-y-1">
        {entries.map(entry => <li key={entry.id}>
          <Link to={`/ai/conversations/${entry.id}`} aria-current={entry.id === activeId ? "page" : undefined}
            className={`block min-h-11 rounded-xl px-3 py-2 text-left focus-visible:outline-brand ${
              entry.id === activeId ? "bg-brand-50 text-brand ring-1 ring-brand-200" : "text-stone-700 hover:bg-stone-50"}`}>
            <span className="block truncate text-sm font-semibold">{entry.title || "New conversation"}</span>
            <span className="block text-xs text-stone-500">{formatDate(entry.updated_at, "MMM d · h:mm a")}</span>
          </Link>
        </li>)}
      </ul>
      {next && <button type="button" onClick={() => void loadMore()} disabled={more}
        className="mt-2 min-h-11 w-full rounded-xl text-sm text-brand underline focus-visible:outline-brand">
        {more ? "Loading…" : "Load more"}</button>}
    </nav>}
  </section>;
}
