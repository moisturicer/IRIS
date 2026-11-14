/**
 * Notifications page -- the full feed, grouped by day, with an Unread filter.
 * The bell in the sidebar answers "is there anything new?"; this page answers
 * "what has happened to my records?".
 *
 * A notification whose task has ended (`resolved_at`, set by the server and
 * never inferred here) is history: it shows a settled line instead of asking
 * for anything, and it is never counted as unread.
 *
 * A notification about a record is one link: the whole row opens the record
 * and marks the notification read, the way the bell's items already do. The
 * mark-read control is a sibling of that link, never nested inside it, so
 * each stays its own focus stop.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { differenceInCalendarDays, formatDistanceToNowStrict, parseISO } from "date-fns";

import { notificationsApi } from "@/api/notifications";
import { useNotificationsStore } from "@/store/notifications.store";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { Notification } from "@/types/notifications";
import { notificationTypeLabel } from "./notificationLabels";
import { SELECTED } from "@/components/ui/highlightRoles";

type Filter = "all" | "unread";

/** Waiting on the reader: unread, and its task has not ended. */
const isUnread = (n: Notification) => !n.is_read && n.resolved_at == null;

/** The day a notification belongs to, in plain words, newest group first. */
function dayGroup(createdAt: string, now: Date): string {
  const days = differenceInCalendarDays(now, parseISO(createdAt));
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return "Earlier this week";
  return "Older";
}

/** "3 hours ago" for today, otherwise the date. */
function when(createdAt: string, now: Date): string {
  const date = parseISO(createdAt);
  return differenceInCalendarDays(now, date) <= 0
    ? formatDistanceToNowStrict(date, { addSuffix: true })
    : formatDate(createdAt);
}

export default function NotificationsPage() {
  const { markRead, markAllRead } = useNotificationsStore();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  // A failed load is not an empty inbox (IR-745): saying "No notifications
  // yet" after an error would tell the reader something untrue.
  const [loadFailed, setLoadFailed] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");

  const load = () => {
    setLoading(true);
    notificationsApi
      .list()
      .then(({ data }) => {
        setNotifications(data.results ?? data);
        setLoadFailed(false);
      })
      .catch(() => setLoadFailed(true))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const setRead = (id: number) => {
    markRead(id);
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
  };

  const handleMarkRead = async (id: number) => {
    await notificationsApi.markRead(id);
    setRead(id);
  };

  // Opening a record is navigation first: a failed read flag is re-synced on
  // the next load and is not worth holding the reader back for.
  const handleOpen = (n: Notification) => {
    if (n.is_read) return;
    setRead(n.id);
    notificationsApi.markRead(n.id).catch(() => undefined);
  };

  const handleMarkAllRead = async () => {
    await notificationsApi.markAllRead();
    markAllRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  const unreadCount = notifications.filter(isUnread).length;

  const groups = useMemo(() => {
    const now = new Date();
    const shown = filter === "unread" ? notifications.filter(isUnread) : notifications;
    const byDay = new Map<string, Notification[]>();
    for (const n of shown) {
      const key = dayGroup(n.created_at, now);
      byDay.set(key, [...(byDay.get(key) ?? []), n]);
    }
    return [...byDay.entries()].map(([label, items]) => ({ label, items, now }));
  }, [notifications, filter]);

  const filterButton = (value: Filter, label: string) => (
    <button
      type="button"
      aria-pressed={filter === value}
      onClick={() => setFilter(value)}
      className={cn(
        "h-9 px-3.5 rounded-lg text-small font-semibold border",
        COLOUR_TRANSITION,
        FOCUS_RING,
        filter === value
          ? SELECTED
          : "border-stone-300 text-stone-700 hover:border-brand hover:text-brand",
      )}
    >
      {label}
    </button>
  );

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Updates on your records and reviews. Select one to open its record."
        actions={
          unreadCount > 0 ? (
            <Button variant="outline" size="sm" onClick={handleMarkAllRead}>
              <i className="fas fa-check-double mr-2" aria-hidden />
              Mark all as read
            </Button>
          ) : undefined
        }
      />

      {!loading && !loadFailed && notifications.length > 0 && (
        <div role="group" aria-label="Show" className="flex items-center gap-2 mb-section-sm">
          {filterButton("all", "All")}
          {filterButton("unread", unreadCount > 0 ? `Unread (${unreadCount})` : "Unread")}
        </div>
      )}

      <div className="bg-surface rounded-2xl border border-stone-200 overflow-hidden">
        {loading ? (
          <Skeleton />
        ) : loadFailed ? (
          <EmptyState
            tone="error"
            icon="fa-circle-exclamation"
            title="Couldn't load your notifications"
            message="Check your connection and try again."
            action={<Button variant="outline" size="sm" onClick={load}>Try again</Button>}
          />
        ) : notifications.length === 0 ? (
          <EmptyState icon="fa-bell-slash" title="No notifications yet." />
        ) : groups.length === 0 ? (
          <EmptyState
            icon="fa-check"
            title="You're all caught up."
            message="Nothing is waiting on you."
            action={<Button variant="outline" size="sm" onClick={() => setFilter("all")}>Show all</Button>}
          />
        ) : (
          groups.map(({ label, items, now }, i) => (
            <section key={label} aria-labelledby={`notif-group-${i}`}>
              <h2
                id={`notif-group-${i}`}
                className={cn(
                  "px-5 py-2 bg-stone-100 text-small font-semibold text-stone-600 border-stone-200",
                  i > 0 && "border-t",
                )}
              >
                {label}
              </h2>
              <ul className="divide-y divide-stone-200 border-t border-stone-200">
                {items.map((n) => (
                  <NotificationRow
                    key={n.id}
                    n={n}
                    time={when(n.created_at, now)}
                    onOpen={() => handleOpen(n)}
                    onMarkRead={() => handleMarkRead(n.id)}
                  />
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </div>
  );
}

interface RowProps {
  n: Notification;
  time: string;
  onOpen: () => void;
  onMarkRead: () => void;
}

function NotificationRow({ n, time, onOpen, onMarkRead }: RowProps) {
  const resolved = n.resolved_at != null;
  const unread = isUnread(n);
  const opens = n.record != null;

  const body = (
    <>
      <span className="sr-only">{unread ? "Unread: " : ""}</span>
      <span
        className={cn(
          "block text-body max-w-[75ch]",
          unread ? "text-stone-900 font-medium" : "text-stone-600",
        )}
      >
        {n.message}
      </span>
      {resolved && (
        // The server's own words, never worked out here (ADR-069): it says what
        // happened and when, so nothing on the row still asks the reader to act.
        <span className="mt-1 flex items-center gap-1.5 text-small font-medium text-stone-700">
          <i className="fas fa-check text-stone-500" aria-hidden />
          {n.resolved_label}
        </span>
      )}
      <span className="mt-1 flex flex-wrap items-center gap-x-2 text-small text-stone-500">
        <time dateTime={n.created_at}>{time}</time>
        {n.notif_type_name && (
          <>
            <span aria-hidden>·</span>
            <span>{notificationTypeLabel(n.notif_type_name)}</span>
          </>
        )}
      </span>
    </>
  );

  return (
    <li
      className={cn(
        "group relative flex items-start gap-3 px-5 py-4",
        COLOUR_TRANSITION,
        opens && "hover:bg-stone-50 [&:has(a:focus-visible)]:ring-2 [&:has(a:focus-visible)]:ring-inset [&:has(a:focus-visible)]:ring-brand",
      )}
    >
      {/* Unread mark: a maroon dot, with the word for screen readers above. */}
      <span
        aria-hidden
        className={cn("mt-2 block w-2 h-2 shrink-0 rounded-full", unread ? "bg-brand" : "bg-transparent")}
      />

      <div className="flex-1 min-w-0">
        {opens ? (
          // The link's ::after covers the whole row, so the row is the target.
          <Link
            to={`/records/${n.record}`}
            onClick={onOpen}
            className="block focus-visible:outline-none after:absolute after:inset-0 after:content-['']"
          >
            {body}
          </Link>
        ) : (
          body
        )}
      </div>

      <div className="relative z-10 flex items-center gap-1 shrink-0 -my-1">
        {unread && (
          <button
            type="button"
            onClick={onMarkRead}
            aria-label="Mark as read"
            title="Mark as read"
            className={cn(
              "w-9 h-9 rounded-lg flex items-center justify-center text-stone-500 hover:bg-stone-100 hover:text-stone-900",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <i className="fas fa-check text-[13px]" aria-hidden />
          </button>
        )}
        {opens && (
          <i
            aria-hidden
            className="fas fa-chevron-right w-9 text-center text-[12px] text-stone-400 group-hover:text-brand pointer-events-none"
          />
        )}
      </div>
    </li>
  );
}
