import { create } from "zustand";

interface Toast {
  id:      string;
  type:    "success" | "error" | "info";
  message: string;
}

const COLLAPSED_KEY = "iris_sidebar_collapsed";

/** Survives reloads; falls back to expanded when storage is unavailable. */
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    /* storage unavailable — the choice still applies for this session */
  }
}

interface UIState {
  /** Mobile sidebar drawer open (desktop sidebar always visible via CSS). */
  sidebarOpen: boolean;
  /** Desktop rail collapsed to icons only. Ignored by the mobile drawer. */
  sidebarCollapsed: boolean;
  toasts:      Toast[];
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar:  () => void;
  closeSidebar:   () => void;
  toggleSidebarCollapsed: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  addToast:       (toast: Omit<Toast, "id">) => void;
  removeToast:    (id: string) => void;
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  sidebarCollapsed: readCollapsed(),
  toasts:      [],

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar:  () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  closeSidebar:   () => set({ sidebarOpen: false }),

  toggleSidebarCollapsed: () =>
    set((s) => {
      writeCollapsed(!s.sidebarCollapsed);
      return { sidebarCollapsed: !s.sidebarCollapsed };
    }),
  setSidebarCollapsed: (collapsed) => {
    writeCollapsed(collapsed);
    set({ sidebarCollapsed: collapsed });
  },

  addToast: (toast) => {
    const id = crypto.randomUUID();
    set((s) => ({ toasts: [...s.toasts, { id, ...toast }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 4000);
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
