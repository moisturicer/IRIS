import type { PageWidth } from "./PageContainer";

/** What a route says about its page, read by the shell and the browser tab. */
export type RouteHandle = {
  /**
   * The page's name, for its browser tab (IR-1073). The page draws its own
   * title; nothing above it repeats the name (IR-1255).
   */
  title?: string;
  /** How wide the page may grow; `AppShell` reads it (IR-521). Standard when absent. */
  width?: PageWidth;
};
