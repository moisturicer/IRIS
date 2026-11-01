import { create } from "zustand";
import type { Notification } from "@/types/notifications";
import { useAuthStore } from "./auth.store";

interface NotificationsState {
  items:       Notification[];
  unreadCount: number;
  setItems:    (items: Notification[]) => void;
  markRead:    (id: number)           => void;
  markAllRead: ()                     => void;
}

export const useNotificationsStore = create<NotificationsState>((set) => ({
  items:       [],
  unreadCount: 0,

  setItems: (items) =>
    set({ items, unreadCount: items.length }),  // caller passes only unread items for the count

  markRead: (id) =>
    set((s) => ({
      items:       s.items.filter((n) => n.id !== id),
      unreadCount: Math.max(0, s.unreadCount - 1),
    })),

  // Clears items too, not just the count. `items` holds only unread rows (see
  // setItems), so leaving them behind would render a populated list against a
  // zeroed badge -- visible in the header bell, which lists from `items`.
  markAllRead: () => set({ items: [], unreadCount: 0 }),
}));

/**
 * Unread notifications belong to one signed-in session (IR-746).
 *
 * This store outlives sign-out -- it is module state, shared by the whole tab
 * -- so without this, the next person to sign in on the same tab saw the
 * previous account's notification text and record links until their own fetch
 * replaced them. `sessionEpoch` moves on every `logout` and `clearTokens`,
 * which is exactly "the session these items were fetched for has ended".
 * Subscribing here keeps the auth store from having to know this one exists.
 */
useAuthStore.subscribe((state, previous) => {
  if (state.sessionEpoch !== previous.sessionEpoch) {
    useNotificationsStore.setState({ items: [], unreadCount: 0 });
  }
});
