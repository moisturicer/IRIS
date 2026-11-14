import { useEffect } from "react";
import { useMatches } from "react-router-dom";

import type { RouteHandle } from "@/components/layout/Breadcrumbs";
import { usePageTitleStore } from "@/store/pageTitle.store";

const SUFFIX = "IRIS";

/** "<page> · IRIS"; the bare product name when a page has no name yet. */
export function formatDocumentTitle(page: string | null | undefined): string {
  const name = page?.trim();
  return name ? `${name} · ${SUFFIX}` : SUFFIX;
}

/**
 * Keeps `document.title` on the deepest route's name (IR-1073, WCAG 2.4.2):
 * its `handle.title`, else its `handle.crumb`, unless the page on screen has
 * published something more specific through `usePageTitle`.
 */
export function useRouteDocumentTitle(): void {
  const matches = useMatches();
  const override = usePageTitleStore((s) => s.override);
  const named = [...matches]
    .reverse()
    .map((m) => {
      const handle = m.handle as RouteHandle | undefined;
      return handle?.title ?? handle?.crumb;
    })
    .find(Boolean);
  const title = formatDocumentTitle(override ?? named);

  useEffect(() => {
    document.title = title;
  }, [title]);
}

/**
 * Names the page more exactly than its route can: a paper's title, a
 * conversation's, a count. `null` or `undefined` leaves the route's own name.
 * It clears itself when the page goes, so one page's name never outlives it.
 */
export function usePageTitle(title: string | null | undefined): void {
  const set = usePageTitleStore((s) => s.set);
  useEffect(() => {
    if (!title) return;
    set(title);
    return () => {
      if (usePageTitleStore.getState().override === title) set(null);
    };
  }, [title, set]);
}
