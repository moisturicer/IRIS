import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { notificationsApi } from "@/api/notifications";
import { useNotificationsStore } from "@/store/notifications.store";
import type { Notification } from "@/types/notifications";
import { formatDate, cn } from "@/lib/utils";

/** How many of the latest unread items the popover shows before deferring to the full page. */
const PREVIEW_LIMIT = 3;

/**
 * The notification bell: at the top of the sidebar, and in the phone bar
 * below `md`. There is no app header any more (IR-519).
 *
 * Complements NotificationsPage rather than replacing it: the page answers
 * "what has happened to my records?" (full history, filterable), the bell
 * answers "is there anything new right now?" without leaving the current
 * screen.
 *
 * Reads from the shared `useNotificationsStore` -- deliberately NOT its own
 * fetch: `AppShell` fetches once for every bell on screen (IR-370). An
 * earlier version fetched independently and the two counters disagreed: marking
 * all read in the bell cleared the bell but left the sidebar showing the old
 * count until a page refresh. One source of truth, two surfaces.
 *
 * Backend needed no changes: /notifications/?unread=true, mark-read and
 * mark-all-read all already existed.
 */
interface NotificationBellProps {
  /**
   * Which edge of the bell the dropdown lines up with. "end" (the default)
   * opens leftward, for a bell near the right of the screen; the sidebar's
   * bell sits at the left of the screen, so it opens rightward with "start".
   */
  align?: "start" | "end";
  /**
   * The native hover title. A caller that wraps the bell in its own `Tooltip`
   * (the sidebar's rail, IR-1086) turns it off so two tips do not stack.
   */
  showTitle?: boolean;
}

export function NotificationBell({ align = "end", showTitle = true }: NotificationBellProps) {
  // AppShell owns the fetch (IR-370); the bell only reads the store.
  const unreadCount = useNotificationsStore((s) => s.unreadCount);
  const items = useNotificationsStore((s) => s.items);
  const markReadInStore = useNotificationsStore((s) => s.markRead);
  const unreadBadge = unreadCount > 9 ? "9+" : String(unreadCount);

  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // Closing hands focus back to the bell, so a keyboard user is not dropped at
  // the top of the page. A pointer click outside leaves focus where it went.
  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

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
        title={showTitle ? "Notifications" : undefined}
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
          className={cn(
            "absolute top-full mt-2 w-[380px] max-w-[calc(100vw-2rem)] max-h-[60vh] flex flex-col bg-overlay rounded-card border border-stone-200 shadow-card-md z-50 overflow-hidden",
            align === "start" ? "left-0" : "right-0",
          )}
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

          <div className="min-h-0 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-6 text-center text-small text-stone-600">
                Nothing new. You&apos;re all caught up.
              </p>
            ) : (
              <ul>
                {items.slice(0, PREVIEW_LIMIT).map((n) => {
                  const resolved = n.resolved_at != null;
                  const body = (
                    <>
                      <span aria-hidden className={cn("mt-1.5 block w-2 h-2 shrink-0 rounded-full", resolved ? "bg-transparent" : "bg-brand")} />
                      <span className="min-w-0 flex-1">
                        <span className={cn("block text-small leading-snug", resolved ? "text-stone-600" : "text-stone-900 font-medium")}>
                          {!resolved && <span className="sr-only">Unread: </span>}
                          {n.message}
                        </span>
                        <span className="block text-label text-stone-600 mt-0.5">
                          {n.record_title ? `${n.record_title} · ` : ""}
                          {formatDate(n.created_at)}
                        </span>
                      </span>
                    </>
                  );
                  const rowClass = "flex items-start gap-3 w-full text-left px-4 py-2.5 hover:bg-stone-50 transition-colors";
                  return (
                    <li key={n.id}>
                      {/* Only link to a record when there is one -- a broadcast
                          notification has no record attached. */}
                      {n.record ? (
                        <Link to={`/records/${n.record}`} onClick={() => void handleOpenItem(n)} className={rowClass}>
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
            )}
          </div>
        </div>
      )}
    </div>
  );
}
