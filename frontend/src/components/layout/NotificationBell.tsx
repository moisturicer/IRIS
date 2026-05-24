import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useNotifications } from "@/hooks/useNotifications";
import { notificationsApi } from "@/api/notifications";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";

/**
 * Header notification dropdown. Full list lives at /notifications.
 * Sidebar keeps a single bell link with badge — avoid duplicating dropdown there.
 */
export function NotificationBell() {
  const { notifications, unreadCount, markRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const handleMarkRead = async (id: number) => {
    await notificationsApi.markRead(id);
    markRead(id);
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "relative w-[34px] h-[34px] rounded-lg border border-slate-200 flex items-center justify-center",
          "text-slate-600 hover:bg-slate-50 transition-colors",
          open && "bg-slate-50 border-slate-300"
        )}
        aria-label="Notifications"
        aria-expanded={open}
      >
        <i className="fas fa-bell text-[13px]" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-[320px] max-h-[400px] bg-white rounded-xl border border-slate-200 shadow-lg z-50 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
            <span className="text-[13px] font-bold text-slate-800">Notifications</span>
            <Link
              to="/notifications"
              onClick={() => setOpen(false)}
              className="text-[11px] font-semibold text-brand hover:underline"
            >
              View all
            </Link>
          </div>

          <div className="overflow-y-auto flex-1 scrollbar-thin">
            {notifications.length === 0 ? (
              <p className="px-4 py-8 text-center text-[12px] text-slate-400">No new notifications</p>
            ) : (
              <ul className="divide-y divide-slate-50">
                {notifications.slice(0, 8).map((n) => (
                  <li key={n.id} className="px-4 py-3 hover:bg-slate-50/80">
                    <p className="text-[12px] text-slate-700 leading-snug">{n.message}</p>
                    <div className="flex items-center justify-between mt-2 gap-2">
                      <span className="text-[10px] text-slate-400">{formatDate(n.created_at)}</span>
                      <div className="flex items-center gap-2">
                        {n.record != null && (
                          <Link
                            to={`/records/${n.record}`}
                            onClick={() => setOpen(false)}
                            className="text-[10px] font-semibold text-brand hover:underline"
                          >
                            View record
                          </Link>
                        )}
                        <button
                          type="button"
                          onClick={() => handleMarkRead(n.id)}
                          className="text-[10px] text-slate-500 hover:text-slate-800"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
