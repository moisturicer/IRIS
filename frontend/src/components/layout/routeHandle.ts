/**
 * What a route says about its page, read by the browser tab.
 *
 * It no longer names a width (IR-1353): every page in the shell sits in the
 * one frame, `PageContainer`, so there is nothing for a route to choose.
 */
export type RouteHandle = {
  /**
   * The page's name, for its browser tab (IR-1073). The page draws its own
   * title; nothing above it repeats the name (IR-1255).
   */
  title?: string;
};
