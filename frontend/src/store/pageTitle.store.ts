import { create } from "zustand";

/**
 * What a page knows about its own name that the route table cannot (IR-1073):
 * the paper's title, the conversation's title, a count. A page publishes it
 * through `usePageTitle`; `RouteTitle` reads it ahead of the route's own name.
 */
interface PageTitleState {
  override: string | null;
  set: (title: string | null) => void;
}

export const usePageTitleStore = create<PageTitleState>((set) => ({
  override: null,
  set: (title) => set({ override: title }),
}));
