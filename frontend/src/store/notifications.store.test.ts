/**
 * The unread-notifications store empties whenever a session ends or another
 * begins (IR-746). The rendered bell is tested in `NotificationBell.test.tsx`;
 * this pins the store's own contract for every surface that reads it, the
 * sidebar's unread badge included.
 */
import { afterEach, describe, expect, it } from "vitest";

import { makeUser, validToken } from "@/test/authFixtures";
import type { Notification } from "@/types/notifications";

import { useAuthStore } from "./auth.store";
import { useNotificationsStore } from "./notifications.store";

const unread: Notification = {
  id: 1,
  notif_type: 1,
  notif_type_name: "review",
  message: "Account A's manuscript was returned",
  record: 41,
  record_title: "Record 41",
  sender: null,
  sender_name: null,
  recipient: null,
  broadcast_to_role: null,
  created_at: "2026-10-31T09:00:00Z",
  is_read: false,
};

function signedInWithUnread() {
  useAuthStore.getState().login(makeUser({ id: 1 }), validToken({ user_id: 1 }), "refresh");
  useNotificationsStore.getState().setItems([unread]);
  expect(useNotificationsStore.getState().unreadCount).toBe(1);
}

afterEach(() => {
  useAuthStore.getState().logout();
});

describe("unread notifications across session changes", () => {
  it.each([
    ["signing out", () => useAuthStore.getState().logout()],
    ["the session being invalidated", () => useAuthStore.getState().clearTokens()],
    [
      "another account signing in over it",
      () => useAuthStore.getState().login(makeUser({ id: 2 }), validToken({ user_id: 2 }), "refresh"),
    ],
  ])("are emptied by %s", (_, endSession) => {
    signedInWithUnread();

    endSession();

    expect(useNotificationsStore.getState().items).toEqual([]);
    expect(useNotificationsStore.getState().unreadCount).toBe(0);
  });
});
