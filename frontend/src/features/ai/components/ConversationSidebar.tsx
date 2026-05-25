import { Link } from "react-router-dom";
import { formatDate } from "@/lib/utils";
import type { Conversation } from "@/types/chat";

interface ConversationSidebarProps {
  conversations:  Conversation[];
  activeId:         string | null;
  open:             boolean;
  onClose:          () => void;
  onSelect:         (id: string) => void;
  onNew:            () => void;
  onDelete:         (id: string) => void;
}

export function ConversationSidebar({
  conversations,
  activeId,
  open,
  onClose,
  onSelect,
  onNew,
  onDelete,
}: ConversationSidebarProps) {
  if (!open) return null;

  return (
    <aside
      className="shrink-0 w-[min(100%,280px)] sm:w-[260px] flex flex-col border-r border-stone-200/80 bg-[#F7F5F2]"
      aria-label="Chat history"
    >
      <div className="flex items-center gap-2 px-3 py-3 border-b border-stone-200/60">
        <span className="text-[11px] font-bold uppercase tracking-wider text-stone-500 flex-1">
          Chat history
        </span>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 rounded-md text-stone-400 hover:bg-white/80 hover:text-stone-700"
          aria-label="Hide chat history"
          title="Hide history"
        >
          <i className="fas fa-chevron-left text-[11px]" />
        </button>
      </div>

      <div className="p-3">
        <button
          type="button"
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#6B0F12] text-white
            font-semibold text-[12px] py-2.5 hover:bg-[#7d1215] shadow-sm transition-colors"
        >
          <i className="fas fa-plus text-[11px]" />
          New chat
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-2 space-y-1">
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
                      ? "bg-white shadow-sm ring-1 ring-stone-200/80 text-stone-900"
                      : "text-stone-700 hover:bg-white/70"
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
                  <i className="fas fa-trash text-[10px]" />
                </button>
              </div>
            );
          })
        )}
      </nav>

      <div className="p-3 border-t border-stone-200/60">
        <Link
          to="/ai/search"
          className="text-[11px] font-medium text-stone-600 hover:text-[#6B0F12] flex items-center gap-2"
        >
          <i className="fas fa-search text-[10px] text-stone-400" />
          Semantic search
        </Link>
      </div>
    </aside>
  );
}
