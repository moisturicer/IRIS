import { useEffect } from "react";
import { useNotificationsStore } from "@/store/notifications.store";
import { notificationsApi } from "@/api/notifications";
import { useAuthStore } from "@/store/auth.store";
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
    // The session this fetch is for (IR-746). A request sent before a sign-out
    // can answer after the next person has signed in on the same tab; writing
    // it then would show them the previous account's notifications.
    const sessionEpochAtFetch = useAuthStore.getState().sessionEpoch;
    notificationsApi
      .list(true)
      .then(({ data }) => {
        if (useAuthStore.getState().sessionEpoch !== sessionEpochAtFetch) return;
        setItems(data.results);
      })
      .catch(() => {
        /* The store was emptied when the last session ended, so a failed
           fetch leaves the bell empty rather than showing anyone else's
           notifications. The next mount tries again. */
      });
  }, [isAuthenticated, setItems]);

  return { notifications: items, unreadCount, markRead, markAllRead };
}
