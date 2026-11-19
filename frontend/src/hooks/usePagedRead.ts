import { useEffect, useRef, useState, type DependencyList } from "react";

import { useApiRead, type ApiReadStatus } from "@/hooks/useApiRead";

/** One page of a paged list, and whether the server has another after it. */
export interface Page<T> {
  results: T[];
  next: string | null;
}

/**
 * Narrows an API's paged answer to a `Page`, for use inside a read:
 * `api.list(...).then(({ data }) => toPage(data))`.
 */
export function toPage<T>(data: { results?: T[]; next?: string | null }): Page<T> {
  return { results: data.results ?? [], next: data.next ?? null };
}

/**
 * The query parameter for a page. The first page is asked for as the API
 * always has been, with no `page`, and only a later one names it.
 */
export function pageParam(page: number): { page?: number } {
  return page > 1 ? { page } : {};
}

/**
 * The pages read after the first, kept with the first page they follow. When a
 * filter change or a reload brings a new first page, these no longer follow it
 * and are ignored, so nothing stale is ever shown beside a fresh read.
 */
interface LaterPages<T> {
  after: Page<T>;
  rows: T[];
  page: number;
  next: string | null;
}

export interface PagedRead<T> {
  status: ApiReadStatus;
  /** Why the first page failed, when `status` is `failed`. */
  error: unknown;
  /** Every row read so far, in the order the server gave them. */
  rows: T[];
  /** The server has another page after the last one read. */
  hasMore: boolean;
  loadingMore: boolean;
  /** Set when the next page could not be read; what is shown stays. */
  moreError: string | null;
  /** Reads the page after the last one shown and appends it. */
  loadMore: () => void;
  /** Reads again from the first page. */
  retry: () => void;
  /** Read the first page again quietly (ADR-073); see `useApiRead`. */
  refresh: () => void;
}

const MORE_FAILED = "Could not load more. Please try again.";

/**
 * A list the API pages (IR-1100): the first page under `useApiRead`, then
 * "Load more" reads the next page and appends it.
 *
 * `readPage(page, signal)` reads one page, 1-based. The first page is read
 * under `useApiRead`'s rules (IR-914): cancelled when `deps` change or the
 * screen closes, so a slow earlier answer never replaces a newer one. A later
 * page is cancelled by the same events, and its answer is also ignored if the
 * first page it followed has been replaced.
 *
 * A change of `deps`, or `retry`, starts again from the first page.
 */
export function usePagedRead<T>(
  readPage: (page: number, signal: AbortSignal) => Promise<Page<T>>,
  deps: DependencyList,
): PagedRead<T> {
  const read = useApiRead((signal) => readPage(1, signal), deps);
  const firstPage = read.data;

  const [later, setLater] = useState<LaterPages<T> | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const reading = useRef(false);

  // A new first page (or its loss) ends whatever was being read after the old
  // one, and clears its failure.
  useEffect(() => {
    reading.current = false;
    setLoadingMore(false);
    setMoreError(null);
    return () => controller.current?.abort();
  }, [firstPage]);

  const following = later && later.after === firstPage ? later : null;
  const rows = [...(firstPage?.results ?? []), ...(following?.rows ?? [])];
  const hasMore = (following ? following.next : firstPage?.next) != null;

  const loadMore = async () => {
    // The ref, not `loadingMore`: two clicks before a re-render both see the
    // state as false, and the second would orphan the first read's controller.
    if (!firstPage || reading.current) return;
    reading.current = true;
    const page = (following?.page ?? 1) + 1;
    const own = new AbortController();
    controller.current = own;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const data = await readPage(page, own.signal);
      if (own.signal.aborted) return;
      setLater({
        after: firstPage,
        rows: [...(following?.rows ?? []), ...data.results],
        page,
        next: data.next,
      });
    } catch {
      if (own.signal.aborted) return;
      setMoreError(MORE_FAILED);
    } finally {
      // An aborted read was ended by the effect above, which already reset this.
      if (!own.signal.aborted) {
        reading.current = false;
        setLoadingMore(false);
      }
    }
  };

  const retry = () => {
    setMoreError(null);
    read.retry();
  };

  return {
    status: read.status,
    error: read.error,
    rows,
    hasMore,
    loadingMore,
    moreError,
    loadMore,
    retry,
    refresh: read.refresh,
  };
}
