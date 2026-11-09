import { Link } from "react-router-dom";
import { cn, formatDate } from "@/lib/utils";
import type { ReaderConversationSummary } from "@/api/runtimeReader";

interface ConversationSidebarProps {
  conversations:    ReaderConversationSummary[];
  activeId:         string | null;
  open:             boolean;
  onDelete:         (id: string) => void;
  onNewChat:        () => void;
  onCollapse:       () => void;
}

export function ConversationSidebar({
  conversations,
  activeId,
  open,
  onDelete,
  onNewChat,
  onCollapse,
}: ConversationSidebarProps) {
  return (
    <aside
      // Collapses by width so the transition matches the main sidebar, and the
      // toggle stays in the toolbar rather than floating over the chat title.
      className={cn(
        "shrink-0 flex flex-col bg-canvas overflow-hidden transition-[width] duration-200 ease-out",
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
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-800">
          <i className="fas fa-angles-left text-[13px]" aria-hidden />
        </button>
      </div>

      <ConversationHistoryList conversations={conversations} activeId={activeId} onDelete={onDelete} />

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
  onDelete,
}: Omit<ConversationSidebarProps, "open" | "onNewChat" | "onCollapse">) {
  return (
    <nav className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-thin px-2 py-2 space-y-1">
      {conversations.length === 0 ? (
        <p className="px-3 py-6 text-[13px] text-stone-500 text-center">
          Your past chats will appear here.
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
                className={`block w-full text-left rounded-xl px-3 py-2.5 transition-all
                  ${active
                    ? "bg-stone-200/70 text-stone-900"
                    : "text-stone-700 hover:bg-stone-50"
                  }`}
              >
                <span className="block text-[14px] font-semibold truncate pr-6">
                  {c.title || "New conversation"}
                </span>
                <span className="block text-[12px] text-stone-600 mt-0.5">
                  {formatDate(c.updated_at, "MMM d · h:mm a")}
                </span>
              </Link>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
                // Shown on hover or focus with a pointer; always on touch, which has
                // no hover to reveal it, at a 44px target (IR-570).
                className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center p-1.5 rounded-md
                  opacity-0 group-hover:opacity-100 focus-visible:opacity-100
                  [@media(hover:none)]:opacity-100 [@media(hover:none)]:w-11 [@media(hover:none)]:h-11
                  text-stone-600 hover:text-brand-dark hover:bg-brand-50"
                aria-label={`Delete ${c.title || "New conversation"}`}
              >
                <i className="fas fa-trash text-[11px]" aria-hidden />
              </button>
            </div>
          );
        })
      )}
    </nav>
  );
}

/** Starts a new conversation; heads the history list wherever it is shown. */
export function NewChatButton({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className="inline-flex min-h-10 min-w-0 flex-1 items-center justify-center gap-2 rounded-xl bg-brand px-3 text-[14px] font-semibold text-white transition-colors hover:bg-brand-dark">
      <i className="fas fa-plus text-[11px]" aria-hidden />
      New chat
    </button>
  );
}
