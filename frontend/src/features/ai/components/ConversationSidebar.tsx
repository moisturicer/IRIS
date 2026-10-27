import { Link } from "react-router-dom";
import { conversationPath } from "@/lib/askHandoff";
import { cn, formatDate } from "@/lib/utils";
import type { ConversationSummary } from "@/types/ai";

interface ConversationSidebarProps {
  conversations:  ConversationSummary[];
  activeId:         number | null;
  open:             boolean;
  onDelete:         (id: number) => void;
}

export function ConversationSidebar({
  conversations,
  activeId,
  open,
  onDelete,
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
      <div className="w-[min(100vw,280px)] sm:w-[260px] flex flex-col h-full">
      {/* One collapse control only — it lives in ChatToolbar, beside the chat
          title. A second copy here made the same action appear twice.

          min-h-[56px] is shared with ChatToolbar so the two border-b rules meet
          as one continuous line across the split. Without it this header was
          41px against the toolbar's 55px (its title block is two lines) and the
          rule visibly stepped down at the divider. px-5 lines the label up with
          the conversation titles below, which sit at nav px-2 + button px-3. */}
      <div className="flex items-center gap-2 px-5 py-2 min-h-[56px] border-b border-stone-200/80">
        <span className="text-[13px] font-bold uppercase tracking-wider text-stone-500 flex-1">
          Chat history
        </span>
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
}: Omit<ConversationSidebarProps, "open">) {
  return (
    <nav className="flex-1 overflow-y-auto scrollbar-thin px-2 py-2 space-y-1">
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
                to={conversationPath(c.id)}
                aria-current={active ? "page" : undefined}
                className={`block w-full text-left rounded-xl px-3 py-2.5 transition-all
                  ${active
                    ? "bg-brand-50 ring-1 ring-brand-200 text-brand"
                    : "text-stone-700 hover:bg-stone-50"
                  }`}
              >
                <span className="block text-[14px] font-semibold truncate pr-6">
                  {c.title || "New conversation"}
                </span>
                <span className="block text-[12px] text-stone-400 mt-0.5">
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
                  text-stone-400 hover:text-red-600 hover:bg-red-50/80"
                aria-label={`Delete ${c.title}`}
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
