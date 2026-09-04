import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { notificationsApi } from "@/api/notifications";
import { useNotificationsStore } from "@/store/notifications.store";
import { useNotifications } from "@/hooks/useNotifications";
import type { Notification } from "@/types/notifications";
import { formatDate, cn } from "@/lib/utils";

/** How many unread items the dropdown shows before deferring to the full page. */
const PREVIEW_LIMIT = 5;

/**
 * Header notification bell.
 *
 * Complements NotificationsPage rather than replacing it: the page answers
 * "what has happened to my records?" (full history, filterable), the bell
 * answers "is there anything new right now?" without leaving the current
 * screen.
 *
 * Reads from the shared `useNotificationsStore`, which the sidebar's unread
 * badge already uses -- deliberately NOT its own fetch. An earlier version
 * fetched independently and the two counters immediately disagreed: marking
 * all read in the bell cleared the bell but left the sidebar showing the old
 * count until a page refresh. One source of truth, two surfaces.
 *
 * Backend needed no changes: /notifications/?unread=true, mark-read and
 * mark-all-read all already existed.
 */
export function NotificationBell() {
  // Shares the mount-time fetch the sidebar already performs.
  const { unreadCount } = useNotifications();
  const items = useNotificationsStore((s) => s.items);
  const markReadInStore = useNotificationsStore((s) => s.markRead);
  const markAllReadInStore = useNotificationsStore((s) => s.markAllRead);

  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click and on Escape -- a dropdown that traps the page is
  // worse than no dropdown.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Optimistic in both handlers: the bell is a glance surface, and a spinner
  // would take longer than the information is worth. The store is the shared
  // truth, so the sidebar badge moves at the same instant.
  const handleMarkAllRead = async () => {
    markAllReadInStore();
    try {
      await notificationsApi.markAllRead();
    } catch {
      /* left cleared locally; the next mount-time fetch re-syncs */
    }
  };

  const handleOpenItem = async (n: Notification) => {
    setOpen(false);
    markReadInStore(n.id);
    try {
      await notificationsApi.markRead(n.id);
    } catch {
      /* same -- a stale read flag is not worth blocking navigation over */
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="true"
        title="Notifications"
        className="relative w-[34px] h-[34px] rounded-lg border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-50 transition-colors"
      >
        <i className="fas fa-bell text-[14px]" aria-hidden />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[17px] h-[17px] px-1 rounded-full bg-brand text-white text-[10px] font-bold flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Notifications"
          className="absolute right-0 top-full mt-2 w-[22rem] max-w-[calc(100vw-2rem)] bg-white rounded-xl border border-stone-200 shadow-card-md z-50 overflow-hidden"
        >
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-stone-100">
            <p className="text-[12px] font-bold uppercase tracking-wider text-stone-400">
              Notifications
            </p>
            {items.length > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="text-[11px] font-semibold text-brand hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-80 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-6 text-center text-[12px] text-stone-400">
                Nothing new. You&apos;re all caught up.
              </p>
            ) : (
              <ul className="divide-y divide-stone-100">
                {items.slice(0, PREVIEW_LIMIT).map((n) => {
                  const body = (
                    <>
                      <p className="text-[12px] text-stone-700 leading-snug">{n.message}</p>
                      <p className="text-[11px] text-stone-400 mt-0.5">
                        {n.record_title ? `${n.record_title} · ` : ""}
                        {formatDate(n.created_at)}
                      </p>
                    </>
                  );
                  return (
                    <li key={n.id}>
                      {/* Only link to a record when there is one -- a broadcast
                          notification has no record attached. */}
                      {n.record ? (
                        <Link
                          to={`/records/${n.record}`}
                          onClick={() => void handleOpenItem(n)}
                          className="block px-4 py-2.5 hover:bg-stone-50 transition-colors"
                        >
                          {body}
                        </Link>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void handleOpenItem(n)}
                          className="block w-full text-left px-4 py-2.5 hover:bg-stone-50 transition-colors"
                        >
                          {body}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <Link
            to="/notifications"
            onClick={() => setOpen(false)}
            className={cn(
              "block px-4 py-2.5 border-t border-stone-100 text-center text-[12px] font-semibold",
              "text-brand hover:bg-stone-50 transition-colors",
            )}
          >
            View all notifications
          </Link>
        </div>
      )}
    </div>
  );
}
