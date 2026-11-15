/**
 * What "unread" means, and how a notification is grouped and dated, once, for
 * the bell and the page (IR-1137).
 *
 * Waiting on the reader: not read, and its task has not ended. A resolved
 * notification (ADR-069) is history, never unread.
 */
import { differenceInCalendarDays, formatDistanceToNowStrict, parseISO } from "date-fns";

import { cn, formatDate } from "@/lib/utils";
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

/**
 * The server's settled line as a small outlined pill with a check (ADR-069):
 * what happened and when, so nothing on the row still asks the reader to act.
 */
export function ResolvedPill({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-stone-900 px-2.5 py-0.5 text-label font-semibold text-stone-900">
      <i className="fas fa-check text-3xs" aria-hidden />
      {label}
    </span>
  );
}

/** The band a notification sits under: Today, Yesterday, This week, then Earlier. */
export function dayGroup(createdAt: string, now: Date): string {
  const days = differenceInCalendarDays(now, parseISO(createdAt));
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "This week";
  return "Earlier";
}

/** "3 hours ago" for today, otherwise "29 Oct". */
export function when(createdAt: string, now: Date): string {
  const date = parseISO(createdAt);
  return differenceInCalendarDays(now, date) <= 0
    ? formatDistanceToNowStrict(date, { addSuffix: true })
    : formatDate(createdAt, "d MMM");
}

/** Items in their given order, split into consecutive-by-label groups. */
export function groupByDay<T extends Notification>(items: T[], now: Date): { label: string; items: T[] }[] {
  const byDay = new Map<string, T[]>();
  for (const n of items) {
    const key = dayGroup(n.created_at, now);
    byDay.set(key, [...(byDay.get(key) ?? []), n]);
  }
  return [...byDay.entries()].map(([label, group]) => ({ label, items: group }));
}

/** The grey band that names a group, inset and rounded as in the prototype. */
export const GROUP_BAND =
  "mx-2 my-1.5 rounded-control bg-stone-100 px-3 py-1.5 text-small font-semibold text-stone-600";
