import { useEffect } from "react";
import { useNotificationsStore } from "@/store/notifications.store";
import { notificationsApi } from "@/api/notifications";
import { useAuth } from "./useAuth";

/**
 * Fetches unread notifications on mount and sets the store.
 * TODO: replace with WebSocket subscription when channels is implemented.
 */
export function useNotifications() {
  const { isAuthenticated } = useAuth();
  const { items, unreadCount, setItems, markRead, markAllRead } = useNotificationsStore();

  useEffect(() => {
    if (!isAuthenticated) return;
    notificationsApi.list(true).then(({ data }) => setItems(data.results));
  }, [isAuthenticated]);

  return { notifications: items, unreadCount, markRead, markAllRead };
}
