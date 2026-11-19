import { useEffect, useState } from "react";
import { useNotificationsStore } from "@/store/notifications.store";
import { notificationsApi } from "@/api/notifications";
import { useAuthStore } from "@/store/auth.store";
import { useLiveRefresh } from "./useLiveRefresh";

/**
 * Fetches the unread notifications into the shared store, once per signed-in
 * session. Call it from exactly one place -- `AppShell` -- not from a bell.
 *
 * Up to three bells are on screen at once (the sidebar, the phone bar, Ask
 * IRIS's toolbar). When each fetched on mount, one page load asked for the
 * same list two or three times (IR-370). Bells read `useNotificationsStore`.
 *
 * Keyed on `sessionEpoch` as well as `isAuthenticated`, so signing in as
 * someone else without signing out first still fetches for the new session.
 * Fetched again on a `notifications` hint, a reconnect or focus (ADR-073,
 * which also covers IR-1033's refetch on focus).
 */
export function useUnreadNotificationsFetch() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const sessionEpoch = useAuthStore((s) => s.sessionEpoch);
  const setItems = useNotificationsStore((s) => s.setItems);
  const [tick, setTick] = useState(0);
  useLiveRefresh(["notifications"], () => setTick((t) => t + 1), isAuthenticated);

  useEffect(() => {
    if (!isAuthenticated) return;
    // The session this fetch is for (IR-746). A request sent before a sign-out
    // can answer after the next person has signed in on the same tab; writing
    // it then would show them the previous account's notifications.
    notificationsApi
      .list(true)
      .then(({ data }) => {
        if (useAuthStore.getState().sessionEpoch !== sessionEpoch) return;
        setItems(data.results, data.count);
      })
      .catch(() => {
        /* The store was emptied when the last session ended, so a failed
           fetch leaves the bell empty rather than showing anyone else's
           notifications. The next session, or page load, tries again. */
      });
  }, [isAuthenticated, sessionEpoch, setItems, tick]);
}
