/**
 * What "unread" means, once, for the bell and the page (IR-1137).
 *
 * Waiting on the reader: not read, and its task has not ended. A resolved
 * notification (ADR-069) is history, never unread.
 */
import { cn } from "@/lib/utils";
import type { Notification } from "@/types/notifications";

export const isUnread = (n: Notification) => !n.is_read && n.resolved_at == null;

/** The maroon dot that marks an unread row; transparent otherwise, so text stays aligned. */
export function UnreadDot({ unread, className }: { unread: boolean; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("block w-2 h-2 shrink-0 rounded-full", unread ? "bg-brand" : "bg-transparent", className)}
    />
  );
}

/** The word a screen reader hears where sighted readers see the dot. */
export function UnreadWord({ unread }: { unread: boolean }) {
  return unread ? <span className="sr-only">Unread: </span> : null;
}
