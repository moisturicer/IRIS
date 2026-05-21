import { create } from "zustand";

interface Toast {
  id:      string;
  type:    "success" | "error" | "info";
  message: string;
}

interface UIState {
  sidebarOpen: boolean;
  toasts:      Toast[];
  toggleSidebar: () => void;
  addToast:      (toast: Omit<Toast, "id">) => void;
  removeToast:   (id: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  toasts:      [],

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  addToast: (toast) => {
    const id = crypto.randomUUID();
    set((s) => ({ toasts: [...s.toasts, { id, ...toast }] }));
    // Auto-remove after 4 seconds
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000);
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
