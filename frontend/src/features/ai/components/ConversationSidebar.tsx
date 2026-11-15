import { useId } from "react";
import { Link } from "react-router-dom";
import { cn, formatDate } from "@/lib/utils";
import type { ReaderConversationSummary } from "@/api/runtimeReader";
import { EarlierConversationList } from "./EarlierConversations";
import { HERE } from "@/components/ui/highlightRoles";

/** The history search and paging, from `useConversationHistory`. */
export interface HistorySearch {
  text:        string;
  onText:      (text: string) => void;
  query:       string;
  state:       "loading" | "ready" | "error";
  hasMore:     boolean;
  loadingMore: boolean;
  onMore:      () => void;
}

interface ConversationSidebarProps {
  conversations:    ReaderConversationSummary[];
  activeId:         string | null;
  open:             boolean;
  search:           HistorySearch;
  onDelete:         (id: string) => void;
  onNewChat:        () => void;
  onCollapse:       () => void;
}

export function ConversationSidebar({
  conversations,
  activeId,
  open,
  search,
  onDelete,
  onNewChat,
  onCollapse,
}: ConversationSidebarProps) {
  return (
    <aside
      // Collapses by width so the transition matches the main sidebar, and the
      // toggle stays in the toolbar rather than floating over the chat title.
      className={cn(
        "shrink-0 flex flex-col bg-stone-50 overflow-hidden transition-[width] duration-200 ease-out",
        // `invisible` also drops the collapsed panel out of the tab order.
        open
          ? "w-[min(100%,280px)] sm:w-[260px] border-r border-stone-200"
          : "w-0 border-r-0 invisible",
      )}
      aria-label="Chat history"
      aria-hidden={!open}
    >
      <div className="w-[min(100vw,280px)] sm:w-[260px] flex flex-col h-full min-h-0">
      {/* New chat and the collapse control sit together at the head of the list.
          min-h-[56px] is shared with ChatToolbar so the two border-b rules meet
          as one continuous line across the split. */}
      <div className="flex shrink-0 items-center gap-2 px-3 py-2 min-h-[56px] border-b border-stone-200/80">
        <NewChatButton onClick={onNewChat} />
        <button type="button" onClick={onCollapse} aria-label="Hide chat history" title="Hide history"
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-card text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-800">
          <i className="fas fa-angles-left text-small" aria-hidden />
        </button>
      </div>

      <ConversationHistoryList conversations={conversations} activeId={activeId} search={search} onDelete={onDelete} />

      </div>
    </aside>
  );
}

/**
 * The reader's conversations, newest first, each a link to its own address.
 * Beside the answer on a wide page, and in the history drawer on a phone
 * (IR-570), so the two cannot list them differently.
 */
export function ConversationHistoryList({
  conversations,
  activeId,
  search,
  onDelete,
}: Omit<ConversationSidebarProps, "open" | "onNewChat" | "onCollapse">) {
  const searchId = useId();
  return (<>
    <div className="shrink-0 px-3 pt-3">
      <label htmlFor={searchId} className="sr-only">Search your past conversations</label>
      <input id={searchId} type="search" value={search.text} onChange={e => search.onText(e.target.value)}
        placeholder="Search past conversations" autoComplete="off" maxLength={200}
        className="min-h-10 w-full rounded-card border border-stone-200 bg-white px-3 text-control text-stone-900 placeholder:text-stone-500 focus-visible:outline-brand" />
      <p role="status" aria-live="polite" className="px-1 pt-1 text-label text-stone-600">
        {search.query && search.state === "ready" ? `${conversations.length}${search.hasMore ? "+" : ""} found` : ""}
      </p>
    </div>
    <nav aria-label="Past conversations"
      className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-thin px-2 py-2 space-y-1">
      {search.state === "error" && (
        <p className="px-3 py-3 text-small text-stone-700">Could not load your conversations. Try again.</p>
      )}
      {conversations.length === 0 ? (
        search.state === "ready" && <p className="px-3 py-6 text-small text-stone-500 text-center">
          {search.query ? `No conversations match “${search.query}”.` : "Your past chats will appear here."}
        </p>
      ) : (
        conversations.map((c) => {
          const active = c.id === activeId;
          return (
            <div key={c.id} className="group relative">
              {/* A link to the conversation's own address (IR-548), so it
                  opens in a new tab, survives a refresh and joins history. */}
              <Link
                to={`/ai/conversations/${c.id}`}
                aria-current={active ? "page" : undefined}
                className={`block w-full text-left rounded-card px-3 py-2.5 transition-all
                  ${active
                    ? HERE
                    : "text-stone-700 hover:bg-stone-50"
                  }`}
              >
                <span className="block text-body font-semibold truncate pr-6">
                  {c.title || "New conversation"}
                </span>
                <span className="block text-label text-stone-600 mt-0.5">
                  {formatDate(c.updated_at, "MMM d · h:mm a")}
                </span>
              </Link>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
                // Shown on hover or focus with a pointer; always on touch, which has
                // no hover to reveal it, at a 44px target (IR-570).
                className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center p-1.5 rounded-control
                  opacity-0 group-hover:opacity-100 focus-visible:opacity-100
                  [@media(hover:none)]:opacity-100 [@media(hover:none)]:w-11 [@media(hover:none)]:h-11
                  text-stone-600 hover:text-brand-dark hover:bg-stone-100"
                aria-label={`Delete ${c.title || "New conversation"}`}
              >
                <i className="fas fa-trash text-label" aria-hidden />
              </button>
            </div>
          );
        })
      )}
      {search.hasMore && (
        <button type="button" onClick={search.onMore} disabled={search.loadingMore}
          className="min-h-11 w-full rounded-card text-small text-brand underline focus-visible:outline-brand">
          {search.loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </nav>
    {/* Conversations Django answered before IR-957, read-only. */}
    <EarlierConversationList />
  </>);
}

/** Starts a new conversation; heads the history list wherever it is shown. */
export function NewChatButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="inline-flex min-h-10 min-w-0 flex-1 items-center justify-center gap-2 rounded-card bg-brand px-3 text-control font-semibold text-white transition-colors hover:bg-brand-dark">
      <i className="fas fa-plus text-label" aria-hidden />
      New chat
    </button>
  );
}
