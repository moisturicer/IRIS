import { useEffect, useRef, useState } from "react";
import { notificationHref } from "@/features/notifications/notificationHref";
import { Link } from "react-router-dom";
import { notificationsApi } from "@/api/notifications";
import { useNotificationsStore } from "@/store/notifications.store";
import type { Notification } from "@/types/notifications";
import {
  GROUP_BAND, groupByDay, isUnread, ResolvedPill, UnreadDot, UnreadWord, when,
} from "@/features/notifications/unread";
import { cn } from "@/lib/utils";

/** How many of the latest notifications the popover shows before deferring to the full page. */
const PREVIEW_LIMIT = 3;

/**
 * The notification bell, for phones: in the phone bar below `md`, and in Ask
 * IRIS's toolbar, which has no phone bar. From `md` the sidebar's
 * Notifications link carries the same count instead.
 *
 * Complements NotificationsPage rather than replacing it: the page answers
 * "what has happened to my records?" (full history, filterable), the bell
 * answers "is there anything new right now?" without leaving the current
 * screen.
 *
 * The badge reads the shared `useNotificationsStore` -- deliberately NOT its
 * own fetch: `AppShell` fetches once for every bell on screen (IR-370). An
 * earlier version fetched independently and the two counters disagreed: marking
 * all read in the bell cleared the bell but left the sidebar showing the old
 * count until a page refresh. One source of truth, two surfaces.
 *
 * The popover's rows are the latest three of everything, settled ones muted
 * under their own pill, fetched when it opens (IR-1137); until they arrive, or
 * if the fetch fails, it shows the unread items the store already holds.
 *
 * Backend needed no changes: /notifications/?unread=true, mark-read and
 * mark-all-read all already existed.
 */
export function NotificationBell() {
  // AppShell owns the fetch (IR-370); the bell only reads the store.
  const unreadCount = useNotificationsStore((s) => s.unreadCount);
  const items = useNotificationsStore((s) => s.items);
  const markReadInStore = useNotificationsStore((s) => s.markRead);
  const unreadBadge = unreadCount > 9 ? "9+" : String(unreadCount);

  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState<Notification[] | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Closing hands focus back to the bell, so a keyboard user is not dropped at
  // the top of the page. A pointer click outside leaves focus where it went.
  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

  // Newest first, whatever order either source came in.
  const latest = [...(recent ?? items)]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, PREVIEW_LIMIT);
  const groups = groupByDay(latest, new Date());

  // Read and settled items are not in the store, so ask for the latest when the
  // popover opens. A failure leaves the store's unread items showing.
  useEffect(() => {
    if (!open) {
      setRecent(null);
      return;
    }
    let live = true;
    void (async () => {
      try {
        const { data } = await notificationsApi.latest();
        if (live) setRecent(data.results);
      } catch {
        /* the store's unread items stay */
      }
    })();
    return () => { live = false; };
  }, [open]);

  // Close on outside click and on Escape -- a dropdown that traps the page is
  // worse than no dropdown.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Optimistic: the bell is a glance surface, and a spinner would take longer
  // than the information is worth. The store is the shared truth, so the
  // sidebar badge moves at the same instant. "Mark all as read" lives on the
  // Notifications page, not here.
  const handleOpenItem = async (n: Notification) => {
    close(true);
    // Only a waiting item changes the count; opening a read or settled one does not.
    if (!isUnread(n)) return;
    markReadInStore(n.id);
    try {
      await notificationsApi.markRead(n.id);
    } catch {
      /* a stale read flag is not worth blocking navigation over */
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadBadge} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="dialog"
        title="Notifications"
        className="relative w-11 h-11 md:w-[34px] md:h-[34px] touch:w-11 touch:h-11 rounded-control border border-stone-200 flex items-center justify-center text-stone-600 hover:bg-stone-50 transition-colors"
      >
        <i className="fas fa-bell text-body" aria-hidden />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-5 h-5 px-1 rounded-full bg-brand text-white text-label font-bold flex items-center justify-center">
            {unreadBadge}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="absolute right-0 top-full mt-2 w-[380px] max-w-[calc(100vw-2rem)] max-h-[60vh] flex flex-col bg-overlay rounded-card border border-stone-200 shadow-card-md z-50 overflow-hidden"
        >
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-stone-100">
            <p className="text-body font-semibold text-stone-900">Notifications</p>
            <Link
              to="/notifications"
              onClick={() => close(false)}
              className="inline-flex items-center min-h-11 md:min-h-0 touch:min-h-11 text-label font-semibold text-brand hover:underline"
            >
              See all
            </Link>
          </div>

          <div className="min-h-0 overflow-y-auto pb-1.5">
            {latest.length === 0 ? (
              <p className="px-4 py-6 text-center text-small text-stone-600">
                Nothing new. You&apos;re all caught up.
              </p>
            ) : (
              groups.map(({ label, items: group }) => (
                <section key={label} aria-label={label}>
                  <p aria-hidden className={GROUP_BAND}>{label}</p>
                  <ul>
                    {group.map((n) => {
                      const unread = isUnread(n);
                      const body = (
                        <>
                          <UnreadDot unread={unread} className="mt-2" />
                          <span className="min-w-0 flex-1">
                            <span className={cn("block text-body leading-snug", unread ? "text-stone-900 font-medium" : "text-stone-600")}>
                              <UnreadWord unread={unread} />
                              {n.message}
                            </span>
                            <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-stone-500">
                              <time dateTime={n.created_at}>{when(n.created_at, new Date())}</time>
                              {n.resolved_at != null && <ResolvedPill label={n.resolved_label} />}
                            </span>
                          </span>
                        </>
                      );
                      const rowClass = "flex items-start gap-3 w-full text-left px-4 py-3 hover:bg-stone-50 transition-colors";
                      const href = notificationHref(n);
                      return (
                        <li key={n.id}>
                          {/* A link only where there is somewhere to go: a Record, or
                              the page the server names (IR-765). */}
                          {href ? (
                            <Link to={href} onClick={() => void handleOpenItem(n)} className={rowClass}>
                              {body}
                            </Link>
                          ) : (
                            <button type="button" onClick={() => void handleOpenItem(n)} className={rowClass}>
                              {body}
                            </button>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
