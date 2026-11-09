import type { ReaderConversationSummary as ConversationSummary } from "@/api/runtimeReader";
import { cn } from "@/lib/utils";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";

/** What a recent chat is called: its title, else how much of it there is (IR-584). */
export function recentChatLabel(c: ConversationSummary): string {
  return c.title.trim() || "New chat, no questions yet";
}

function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * The reader's own earlier chats about this paper (IR-584). Choosing one
 * only opens it; nothing is sent, and the one on screen says so.
 */
export function RecentChats({
  chats,
  activeId,
  onChoose,
  className,
}: {
  chats: readonly ConversationSummary[];
  activeId: string | null;
  onChoose: (chat: ConversationSummary) => void;
  className?: string;
}) {
  if (chats.length === 0) return null;
  return (
    <ul aria-label="Recent chats about this paper" className={cn("divide-y divide-stone-200 text-left", className)}>
      {chats.map((c) => (
        <li key={c.id}>
          <button
            type="button"
            onClick={() => onChoose(c)}
            aria-current={c.id === activeId ? "true" : undefined}
            className={cn(
              "flex min-h-11 w-full items-center justify-between gap-3 py-2 text-left text-small",
              c.id === activeId ? "font-semibold text-brand" : "text-stone-700 hover:text-brand",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <span className="min-w-0 truncate">{recentChatLabel(c)}</span>
            <span className="shrink-0 text-2xs text-stone-500">{when(c.updated_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
