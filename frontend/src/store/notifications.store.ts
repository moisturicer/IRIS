import { create } from "zustand";
import type { Notification } from "@/types/notifications";

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
