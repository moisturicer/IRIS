import { useEffect } from "react";
import { useNotificationsStore } from "@/store/notifications.store";
import { notificationsApi } from "@/api/notifications";
import { useAuthStore } from "@/store/auth.store";

/**
 * The unread notifications, read from the shared store. Fetches nothing.
 *
 * Every bell calls this, and there can be three on screen at once (the
 * sidebar, the phone bar, Ask IRIS's toolbar). When each one fetched on mount,
 * a single page load asked for the same list two or three times (IR-370).
 * The fetch now has one owner: `useUnreadNotificationsFetch`, in `AppShell`.
 */
export function useNotifications() {
  const { items, unreadCount, markRead, markAllRead } = useNotificationsStore();
  return { notifications: items, unreadCount, markRead, markAllRead };
}

/**
 * Fetches the unread notifications into the shared store, once per signed-in
 * session. Call it from exactly one place -- `AppShell` -- not from a bell.
 *
 * Keyed on `sessionEpoch` as well as `isAuthenticated`, so signing in as
 * someone else without signing out first still fetches for the new session.
 * TODO: replace with WebSocket subscription when channels is implemented.
 */
export function useUnreadNotificationsFetch() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const sessionEpoch = useAuthStore((s) => s.sessionEpoch);
  const setItems = useNotificationsStore((s) => s.setItems);

  useEffect(() => {
    if (!isAuthenticated) return;
    // The session this fetch is for (IR-746). A request sent before a sign-out
    // can answer after the next person has signed in on the same tab; writing
    // it then would show them the previous account's notifications.
    notificationsApi
      .list(true)
      .then(({ data }) => {
        if (useAuthStore.getState().sessionEpoch !== sessionEpoch) return;
        setItems(data.results);
      })
      .catch(() => {
        /* The store was emptied when the last session ended, so a failed
           fetch leaves the bell empty rather than showing anyone else's
           notifications. The next session, or page load, tries again. */
      });
  }, [isAuthenticated, sessionEpoch, setItems]);
}
