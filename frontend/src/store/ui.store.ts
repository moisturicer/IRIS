import { create } from "zustand";

interface Toast {
  id:      string;
  type:    "success" | "error" | "info";
  message: string;
}

interface UIState {
  /** Mobile sidebar drawer open (desktop sidebar always visible via CSS). */
  sidebarOpen: boolean;
  toasts:      Toast[];
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar:  () => void;
  closeSidebar:   () => void;
  addToast:       (toast: Omit<Toast, "id">) => void;
  removeToast:    (id: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  toasts:      [],

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar:  () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  closeSidebar:   () => set({ sidebarOpen: false }),

  addToast: (toast) => {
    const id = crypto.randomUUID();
    set((s) => ({ toasts: [...s.toasts, { id, ...toast }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000);
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
