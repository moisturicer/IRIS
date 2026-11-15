/**
 * Notifications page -- the full feed, grouped by day, with an Unread filter.
 * The bell in the sidebar answers "is there anything new?"; this page answers
 * "what has happened to my records?".
 *
 * A notification whose task has ended (`resolved_at`, set by the server and
 * never inferred here) is history: it shows a settled line instead of asking
 * for anything, and it is never counted as unread.
 *
 * A notification about a record has an Open button: it goes to the record and
 * marks the notification read, the way the bell's items do. A notification with
 * no record has only the mark-read control. Days are the viewer's own, from
 * each timestamp in the browser's time zone (IR-1137).
 */
import { useEffect, useMemo, useState } from "react";
import { differenceInCalendarDays, formatDistanceToNowStrict, parseISO } from "date-fns";

import { notificationsApi } from "@/api/notifications";
import { failureMessage } from "@/lib/readFailure";
import { useNotificationsStore } from "@/store/notifications.store";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { Notification } from "@/types/notifications";
import { notificationTypeLabel } from "./notificationLabels";
import { SELECTED_SEGMENT } from "@/components/ui/highlightRoles";
import { isUnread, UnreadDot, UnreadWord } from "./unread";

const FAILED_LEAD = "Couldn't update your notifications.";

type Filter = "all" | "unread";

/** The day a notification belongs to, in plain words, newest group first. */
function dayGroup(createdAt: string, now: Date): string {
  const days = differenceInCalendarDays(now, parseISO(createdAt));
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return formatDate(createdAt);
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
  const [loadError, setLoadError] = useState<unknown>(null);
  const [filter, setFilter] = useState<Filter>("all");
  // A failed mark-read or mark-all is said, not swallowed: the row would
  // otherwise look read while the server still holds it unread.
  const [actionError, setActionError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    notificationsApi
      .list()
      .then(({ data }) => {
        setNotifications(data.results ?? data);
        setLoadFailed(false);
      })
      .catch((error: unknown) => { setLoadFailed(true); setLoadError(error); })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const setRead = (id: number) => {
    markRead(id);
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)));
  };

  const handleMarkRead = async (id: number) => {
    try {
      await notificationsApi.markRead(id);
      setRead(id);
      setActionError(null);
    } catch (error) {
      setActionError(failureMessage(error, { lead: FAILED_LEAD }));
    }
  };

  // Opening a record is navigation first: a failed read flag is re-synced on
  // the next load and is not worth holding the reader back for.
  const handleOpen = (n: Notification) => {
    if (n.is_read) return;
    setRead(n.id);
    notificationsApi.markRead(n.id).catch(() => undefined);
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationsApi.markAllRead();
      markAllRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setActionError(null);
    } catch (error) {
      setActionError(failureMessage(error, { lead: FAILED_LEAD }));
    }
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
        "min-h-8 touch:min-h-11 px-3 rounded-control text-small font-semibold inline-flex items-center gap-1.5",
        COLOUR_TRANSITION,
        FOCUS_RING,
        filter === value ? SELECTED_SEGMENT : "text-stone-600 hover:text-stone-900",
      )}
    >
      {label}
      {value === "unread" && (
        <>
          {/* A real space, so the accessible name reads "Unread 3". */}
          {" "}
          <span className="tabular-nums opacity-80">{unreadCount}</span>
        </>
      )}
    </button>
  );

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Updates on your records and reviews. Use Open to go to the record."
        actions={
          // Always there, as in the prototype; nothing to do at zero unread.
          <Button variant="outline" size="sm" onClick={handleMarkAllRead} disabled={unreadCount === 0}>
            <i className="fas fa-check-double mr-2" aria-hidden />
            Mark all as read
          </Button>
        }
      />

      {actionError && (
        <p role="alert" className="mb-section-sm text-small font-medium text-brand-dark">
          {actionError}
        </p>
      )}

      {!loading && !loadFailed && notifications.length > 0 && (
        <div
          role="group"
          aria-label="Show"
          className="inline-flex gap-0.5 p-0.5 mb-section-sm rounded-card bg-stone-100 border border-stone-200"
        >
          {filterButton("all", "All")}
          {filterButton("unread", "Unread")}
        </div>
      )}

      <div className="bg-surface rounded-card border border-stone-200 overflow-hidden">
        {loading ? (
          <Skeleton onRetry={load} />
        ) : loadFailed ? (
          <EmptyState
            tone="error"
            icon="fa-circle-exclamation"
            title="Couldn't load your notifications"
            message={failureMessage(loadError)}
            action={<Button variant="outline" size="sm" onClick={load}>Try again</Button>}
          />
        ) : notifications.length === 0 ? (
          <EmptyState icon="fa-bell-slash" title="No notifications yet." />
        ) : groups.length === 0 ? (
          <EmptyState
            icon="fa-check"
            title="You're up to date"
            message="New review activity on your papers appears here."
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

  return (
    <li className="flex items-start gap-3 px-5 py-4 max-sm:flex-wrap">
      {/* Unread mark: a maroon dot, with the word for screen readers beside the text. */}
      <UnreadDot unread={unread} className="mt-2" />

      <div className="flex-1 min-w-0 max-sm:basis-[calc(100%-1.25rem)]">
        <span
          className={cn(
            "block text-body max-w-[75ch]",
            unread ? "text-stone-900 font-medium" : "text-stone-600",
          )}
        >
          <UnreadWord unread={unread} />
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
      </div>

      <div className="flex items-center gap-1 shrink-0 self-center max-sm:ml-5">
        {unread && (
          <button
            type="button"
            onClick={onMarkRead}
            aria-label="Mark as read"
            title="Mark as read"
            className={cn(
              "w-9 h-9 touch:w-11 touch:h-11 rounded-control flex items-center justify-center text-stone-500 hover:bg-stone-100 hover:text-stone-900",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <i className="fas fa-check text-small" aria-hidden />
          </button>
        )}
        {n.record != null && (
          <ButtonLink
            to={`/records/${n.record}`}
            variant="outline"
            size="sm"
            onClick={onOpen}
            aria-label={`Open: ${n.message}`}
          >
            Open
          </ButtonLink>
        )}
      </div>
    </li>
  );
}
