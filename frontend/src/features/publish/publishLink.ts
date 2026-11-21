/**
 * Addresses that open Publish (IR-1258).
 *
 * The Publish dialog is mounted once, in the app shell, and opens over
 * whatever page the address names when it carries `?publish=`. So a link to
 * it keeps the page it is on, query included: from My Library's submissions
 * tab, Continue draft is `/records/mine?section=research&publish=12`, and
 * closing the form (which removes only `publish`) leaves the reader there.
 */
import { useCallback } from "react";
import { useLocation } from "react-router-dom";

/** The query parameter that opens Publish: `new`, or a draft's id. */
export const PUBLISH_PARAM = "publish";

interface At {
  pathname: string;
  search: string;
}

/** The address that opens Publish on `target` over the page at `at`, keeping its query. */
export function publishHref(at: At, target: string | number): string {
  const params = new URLSearchParams(at.search);
  params.set(PUBLISH_PARAM, String(target));
  return `${at.pathname}?${params.toString()}`;
}

/** `publishHref` over the current page. */
export function usePublishHref(): (target: string | number) => string {
  const { pathname, search } = useLocation();
  return useCallback((target: string | number) => publishHref({ pathname, search }, target), [pathname, search]);
}
