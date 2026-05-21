/**
 * Notifications page -- full list with mark-as-read per item and mark-all-read.
 * The bell in the header only shows unread count; this page shows the full feed.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { notificationsApi } from "@/api/notifications";
import { useNotificationsStore } from "@/store/notifications.store";
import { PageHeader }   from "@/components/layout/PageHeader";
import { EmptyState }   from "@/components/shared/EmptyState";
import { Button }       from "@/components/ui/Button";
import { formatDate }   from "@/lib/utils";
import type { Notification } from "@/types/notifications";

export default function NotificationsPage() {
  const { markRead, markAllRead } = useNotificationsStore();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    notificationsApi
      .list()
      .then(({ data }) => setNotifications(data.results ?? data))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleMarkRead = async (id: number) => {
    await notificationsApi.markRead(id);
    markRead(id);
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
    );
  };

  const handleMarkAllRead = async () => {
    await notificationsApi.markAllRead();
    markAllRead();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div>
      <PageHeader
        title="Notifications"
        description="Updates on your records and reviews."
        action={
          unreadCount > 0 ? (
            <Button variant="outline" size="sm" onClick={handleMarkAllRead}>
              Mark all as read
            </Button>
          ) : undefined
        }
      />

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-[13px]">Loading...</div>
        ) : notifications.length === 0 ? (
          <EmptyState icon="fa-bell-slash" title="No notifications yet." />
        ) : (
          <ul className="divide-y divide-gray-100">
            {notifications.map((n) => (
              <li
                key={n.id}
                className={`flex items-start gap-3 px-5 py-4 ${!n.is_read ? "bg-red-50/40" : ""}`}
              >
                {/* Unread dot */}
                <div className="mt-1 shrink-0">
                  {!n.is_read ? (
                    <span className="block w-2 h-2 rounded-full bg-[#6B0F12]" />
                  ) : (
                    <span className="block w-2 h-2 rounded-full bg-transparent" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <p className="text-[13px] text-gray-800">{n.message}</p>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-[12px] text-gray-400">{formatDate(n.created_at)}</span>
                    {n.record_id && (
                      <Link
                        to={`/records/${n.record_id}`}
                        className="text-[12px] text-[#6B0F12] hover:underline"
                      >
                        View record
                      </Link>
                    )}
                  </div>
                </div>

                {!n.is_read && (
                  <button
                    onClick={() => handleMarkRead(n.id)}
                    className="shrink-0 text-[12px] text-gray-400 hover:text-gray-600"
                  >
                    Dismiss
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
