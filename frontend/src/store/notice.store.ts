import { create } from "zustand";

/**
 * Whether the signed-in person must answer the data notice before anything
 * else (ADR-054 decision 3, IR-790).
 *
 * Set from two places: a `notice_acceptance_required` refusal on any request
 * (`api/client.ts`), so a notice published while someone works reaches them on
 * their next request, and `hydrateAuth`, so a refresh lands them back on the
 * screen. Cleared only by answering, or by signing out.
 */
interface NoticeState {
  required: boolean;
  require: () => void;
  clear: () => void;
}

export const useNoticeStore = create<NoticeState>()((set) => ({
  required: false,
  require: () => set({ required: true }),
  clear: () => set({ required: false }),
}));
