import { create } from "zustand";

export interface Toast {
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
  /**
   * Paper mode's rail (IR-569), shown instead of the saved preference while
   * set: collapsed on entry, and the reader may expand it. Never saved.
   */
  readingRail: boolean | null;
  toasts:      Toast[];
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar:  () => void;
  closeSidebar:   () => void;
  toggleSidebarCollapsed: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  /** Collapse to the rail for reading, and close the phone drawer. */
  enterReadingRail: () => void;
  /** Back to the saved preference. */
  leaveReadingRail: () => void;
  addToast:       (toast: Omit<Toast, "id">) => void;
  removeToast:    (id: string) => void;
}

/** Whether the desktop sidebar shows as the rail right now. */
export const selectSidebarCollapsed = (s: UIState) => s.readingRail ?? s.sidebarCollapsed;

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: false,
  sidebarCollapsed: readCollapsed(),
  readingRail: null,
  toasts:      [],

  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar:  () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  closeSidebar:   () => set({ sidebarOpen: false }),

  toggleSidebarCollapsed: () =>
    set((s) => {
      if (s.readingRail !== null) return { readingRail: !s.readingRail };
      writeCollapsed(!s.sidebarCollapsed);
      return { sidebarCollapsed: !s.sidebarCollapsed };
    }),
  enterReadingRail: () => set({ readingRail: true, sidebarOpen: false }),
  leaveReadingRail: () => set({ readingRail: null }),
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
