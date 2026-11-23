import type { ReaderConversationSummary as ConversationSummary } from "@/api/runtimeReader";
import { cn } from "@/lib/utils";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { HERE } from "@/components/ui/highlightRoles";

/** What a recent chat is called: its title, else how much of it there is (IR-584). */
export function recentChatLabel(c: ConversationSummary): string {
  return c.title.trim() || "New chat, no questions yet";
}

/** "Today", "Yesterday", or a short date. */
function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** The pane's hover, shared with Ask IRIS's conversation list (IR-1306). */
const ROW = "hover:bg-brand/[0.07] hover:text-brand-dark " + COLOUR_TRANSITION;

/**
 * The reader's own earlier chats about this paper (IR-584), as a sheet under
 * the Paper Chat header (IR-1306): a heading with the count, New chat first,
 * then each chat with when it was last used, the open one in the Here look.
 * Choosing one only opens it; nothing is sent.
 */
export function RecentChats({
  chats,
  activeId,
  onChoose,
  onNew,
  className,
}: {
  chats: readonly ConversationSummary[];
  activeId: string | null;
  onChoose: (chat: ConversationSummary) => void;
  onNew?: () => void;
  className?: string;
}) {
  return (
    <section aria-label="Chats about this paper" className={cn("motion-safe:animate-fade-in-up", className)}>
      <div className="flex items-baseline justify-between px-1 pb-1.5">
        <h3 className="text-label font-semibold text-stone-700">Chats about this paper</h3>
        <span className="text-label tabular-nums text-stone-500">{chats.length}</span>
      </div>
      {onNew && <button type="button" onClick={onNew}
        className={cn("group flex min-h-11 reading-split:min-h-10 w-full items-center gap-2.5 rounded-control px-2.5 text-left text-small font-medium text-stone-700", ROW, FOCUS_RING)}>
        <span aria-hidden className="inline-flex size-5 items-center justify-center rounded-full text-stone-600 ring-1 ring-stone-300
          transition-colors duration-150 group-hover:bg-brand group-hover:text-white group-hover:ring-brand">
          <i className="fas fa-plus text-3xs" />
        </span>
        New chat
      </button>}
      {chats.length > 0 && <ul aria-label="Recent chats about this paper" className="mt-0.5 space-y-0.5 text-left">
        {chats.map((c) => {
          const active = c.id === activeId;
          return <li key={c.id}>
            <button
              type="button"
              onClick={() => onChoose(c)}
              aria-current={active ? "true" : undefined}
              className={cn(
                "flex min-h-11 reading-split:min-h-10 w-full items-start gap-3 rounded-control px-2.5 py-2 text-left text-small",
                active ? HERE : cn("text-stone-700", ROW),
                FOCUS_RING,
              )}
            >
              <i aria-hidden className={cn("far fa-comment mt-0.5 text-label", active ? "text-brand" : "text-stone-400")} />
              <span className={cn("min-w-0 flex-1 break-words", active && "font-semibold")}>{recentChatLabel(c)}</span>
              <span className="shrink-0 pt-px text-2xs tabular-nums text-stone-500">{when(c.updated_at)}</span>
            </button>
          </li>;
        })}
      </ul>}
    </section>
  );
}
