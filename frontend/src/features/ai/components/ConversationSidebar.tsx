import { cn, formatDate } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

interface ConversationSidebarProps {
  conversations:  Conversation[];
  activeId:         string | null;
  open:             boolean;
  onSelect:         (id: string) => void;
  onDelete:         (id: string) => void;
}

export function ConversationSidebar({
  conversations,
  activeId,
  open,
  onSelect,
  onDelete,
}: ConversationSidebarProps) {
  return (
    <aside
      // Collapses by width so the transition matches the main sidebar, and the
      // toggle stays in the toolbar rather than floating over the chat title.
      className={cn(
        "shrink-0 flex flex-col bg-white overflow-hidden transition-[width] duration-200 ease-out",
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
        <span className="text-[11px] font-bold uppercase tracking-wider text-stone-500 flex-1">
          Chat history
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin px-2 py-2 space-y-1">
        {conversations.length === 0 ? (
          <p className="px-3 py-6 text-[11px] text-stone-500 text-center">
            Your past chats will appear here.
          </p>
        ) : (
          conversations.map((c) => {
            const active = c.id === activeId;
            return (
              <div key={c.id} className="group relative">
                <button
                  type="button"
                  onClick={() => onSelect(c.id)}
                  className={`w-full text-left rounded-xl px-3 py-2.5 transition-all
                    ${active
                      ? "bg-brand-50 ring-1 ring-brand-200 text-brand"
                      : "text-stone-700 hover:bg-stone-50"
                    }`}
                >
                  <span className="block text-[12px] font-semibold truncate pr-6">{c.title}</span>
                  <span className="block text-[10px] text-stone-400 mt-0.5">
                    {formatDate(c.updatedAt, "MMM d · h:mm a")}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDelete(c.id); }}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md opacity-0 group-hover:opacity-100
                    text-stone-400 hover:text-red-600 hover:bg-red-50/80"
                  aria-label={`Delete ${c.title}`}
                >
                  <i className="fas fa-trash text-[10px]" aria-hidden />
                </button>
              </div>
            );
          })
        )}
      </nav>

      </div>
    </aside>
  );
}
