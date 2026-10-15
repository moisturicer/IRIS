import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import { PAGE_WIDTH } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { PUBLISH_PARAM } from "@/features/publish/PublishDialog";
import { useRole } from "@/hooks/useRole";
import { canAccess } from "@/lib/access";
import { cn } from "@/lib/utils";
import { IP_TYPE_LABELS } from "@/types/records";
import type { RecordListItem } from "@/types/records";
import { ALL_VALUE, type FilterOption } from "./DiscoverFilterDropdown";
import {
  activeFilterCount,
  DiscoverFilterBar,
  HAS_IP,
  type DiscoverFilters,
  type DiscoverSort,
} from "./DiscoverFilterBar";
import { DiscoverResultCard } from "./DiscoverResultCard";
import { DiscoverSearchComposer } from "./DiscoverSearchComposer";
import { DiscoverTabs } from "./DiscoverTabs";
import { PaperCiteModal } from "./PaperCiteModal";
import {
  DEFAULT_QUERY,
  discoverQueryKey,
  listParams,
  parseDiscoverQuery,
  writeDiscoverQuery,
  type DiscoverQuery,
} from "./discoverQuery";

const PAGE_SIZE = 12;

/** The list endpoint's `max_page_size` is 100, so at most this many pages
 *  come back in one request when a reader returns. */
const MAX_RESTORED_PAGES = Math.floor(100 / PAGE_SIZE);

/**
 * Where a reader was in a query: how many pages they had loaded and how far
 * they had scrolled. Kept for this tab only, and only for the query it was
 * taken in, so Back or reload brings the same results back (IR-560).
 */
const POSITION_KEY = "iris.discover.position";

interface Position {
  key: string;
  pages: number;
  scrollY: number;
}

function readPosition(key: string): Position | null {
  try {
    const stored = JSON.parse(sessionStorage.getItem(POSITION_KEY) ?? "null") as Position | null;
    return stored && stored.key === key ? stored : null;
  } catch {
    return null;
  }
}

function writePosition(position: Position) {
  try {
    sessionStorage.setItem(POSITION_KEY, JSON.stringify(position));
  } catch {
    // Storage unavailable: Back starts at the first page, which is still correct.
  }
}

/**
 * Discover: find published research, and start a submission (IR-407, F2;
 * spec §4.3).
 *
 * Every control maps to a query param the list endpoint already understands,
 * and filtering is server-side, so a match beyond the first page is never
 * missed. The URL holds the query (`discoverQuery.ts`), so Back, reload and a
 * copied link restore it, and every page fetch is fenced by it (IR-560). The old saved views are gone: Latest and Most viewed are Sort, IP &
 * Patents and Theses are filters, and "For you" -- which had no personalisation
 * signal to rank on -- is removed rather than kept as a relabelled recency feed.
 */
export default function DiscoverPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // react-router's functional `setSearchParams` builds from the URL of the
  // render that created it, so a timer must call the latest one: an older one
  // writes back a URL that predates anything set since (IR-554).
  const latestSetSearchParams = useRef(setSearchParams);
  latestSetSearchParams.current = setSearchParams;
  const { roleName } = useRole();
  // The access map is the one place that says who authors (Student, Adviser).
  const canPublish = canAccess(roleName as never, "submit");

  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failed, setFailed] = useState(false);
  const [loadMoreFailed, setLoadMoreFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  /* ── The query lives in the URL; this is its one parsed form ────────── */
  const query = useMemo(() => parseDiscoverQuery(searchParams), [searchParams]);
  const queryKey = discoverQueryKey(query);
  const { q: activeQuery, filters, sort } = query;

  const [searchInput, setSearchInput] = useState(query.q);

  /* The box follows the URL when it changes underneath it -- the sidebar's
     Discover link, or Clear filters -- but never while the reader is typing,
     since only a change to `q` itself runs this. */
  useEffect(() => {
    setSearchInput((typed) => (typed.trim() === query.q ? typed : query.q));
  }, [query.q]);

  const [tab, setTab] = useState("research");

  const [classifications, setClassifications] = useState<FilterOption[]>([]);
  const [colleges, setColleges] = useState<FilterOption[]>([]);
  const [recordTypes, setRecordTypes] = useState<FilterOption[]>([]);
  const [years, setYears] = useState<string[]>([]);
  const [refLoading, setRefLoading] = useState(true);
  const [refFailed, setRefFailed] = useState(false);
  const [refAttempt, setRefAttempt] = useState(0);

  const [citeRecord, setCiteRecord] = useState<RecordListItem | null>(null);

  /* A hand-edited or stale URL is corrected to what was understood. */
  useEffect(() => {
    const canonical = writeDiscoverQuery(searchParams, query);
    if (canonical.toString() !== searchParams.toString()) {
      setSearchParams(canonical, { replace: true });
    }
  }, [searchParams, query, setSearchParams]);

  /** Every query change goes through here, applied to the URL as it is when
   *  the change lands, so two changes in one tick both survive. */
  const updateQuery = useCallback(
    (change: (current: DiscoverQuery) => DiscoverQuery) =>
      latestSetSearchParams.current(
        (prev) => writeDiscoverQuery(prev, change(parseDiscoverQuery(prev))),
        { replace: true },
      ),
    [],
  );
  const setFilters = (next: DiscoverFilters) => updateQuery((current) => ({ ...current, filters: next }));
  const setSort = (next: DiscoverSort) => updateQuery((current) => ({ ...current, sort: next }));

  /* ── Reference data drives every filter list ────────────────────────── */
  useEffect(() => {
    let cancelled = false;
    setRefLoading(true);
    setRefFailed(false);

    Promise.allSettled([
      recordsApi.classifications(),
      accountsApi.colleges(),
      recordsApi.recordTypes(),
      // Years come from the whole catalogue, not the cards loaded so far, so a
      // Record beyond the first page can still be filtered to (IR-560).
      recordsApi.facets(),
    ])
      .then(([classRes, collegeRes, typeRes, facetRes]) => {
        if (cancelled) return;
        setRefFailed([classRes, collegeRes, typeRes, facetRes].some((r) => r.status === "rejected"));
        if (classRes.status === "fulfilled") {
          setClassifications(
            (classRes.value.data.results ?? []).map((c) => ({ value: String(c.id), label: c.name })),
          );
        }
        if (collegeRes.status === "fulfilled") {
          setColleges(
            (collegeRes.value.data.results ?? []).map((c) => ({ value: String(c.id), label: c.name })),
          );
        }
        if (typeRes.status === "fulfilled") {
          setRecordTypes(
            (typeRes.value.data.results ?? [])
              // A Proposal is never in the catalogue (IR-264, ADR-021 §13), so
              // a Proposal filter could only ever return an empty page.
              .filter((t) => t.name !== "Proposal")
              .map((t) => ({ value: String(t.id), label: t.name })),
          );
        }
        if (facetRes.status === "fulfilled") {
          setYears((facetRes.value.data.years ?? []).map(String));
        }
      })
      .finally(() => {
        if (!cancelled) setRefLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [refAttempt]);

  /* ── Debounce the search box into the query + the URL ───────────────── */
  useEffect(() => {
    const handle = setTimeout(() => {
      updateQuery((current) => ({ ...current, q: searchInput.trim() }));
    }, 300);

    return () => clearTimeout(handle);
    // Only the typed text starts the debounce; `updateQuery` reads the setter
    // through a ref, so it is the current one when the timer fires (IR-554).
  }, [searchInput, updateQuery]);

  /* ── Results, fenced by the query they were asked for ───────────────── */
  // Every response carries the generation it was requested in; a newer query
  // (or a retry) starts a new one, and anything older is dropped, Load more
  // included, so results from two queries can never mix.
  const generation = useRef(0);
  const restoreScrollTo = useRef<number | null>(null);
  /** Where the reader is, set only once this query's results are on screen:
   *  until then there is nothing of this query to return to. */
  const position = useRef<Omit<Position, "scrollY"> | null>(null);

  useEffect(() => {
    const current = ++generation.current;
    position.current = null;
    const restored = readPosition(queryKey);
    const pages = Math.min(Math.max(restored?.pages ?? 1, 1), MAX_RESTORED_PAGES);
    // A depth past the cap comes back shorter, so its scroll offset would land
    // somewhere the reader never was; start at the top instead.
    restoreScrollTo.current = restored && restored.pages <= MAX_RESTORED_PAGES ? restored.scrollY : null;

    setLoading(true);
    setFailed(false);
    setLoadingMore(false);
    setLoadMoreFailed(false);

    recordsApi
      // A returning reader gets every page they had, in one request.
      .list({ ...listParams(query), page: 1, page_size: PAGE_SIZE * pages })
      .then(({ data }) => {
        if (current !== generation.current) return;
        const results = data.results ?? [];
        setRecords(results);
        setTotalCount(data.count ?? results.length);
        // Whole pages only: if the server returned fewer rows than asked, the
        // next Load more re-reads the partial page and duplicates are dropped.
        const loaded = Math.max(1, Math.floor(results.length / PAGE_SIZE));
        setPage(loaded);
        position.current = { key: queryKey, pages: loaded };
      })
      .catch(() => {
        if (current !== generation.current) return;
        setRecords([]);
        setTotalCount(null);
        setFailed(true);
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
    // `query` is fully described by `queryKey`; keying on the string keeps an
    // unrelated URL change (the Publish dialog) from refetching.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, attempt]);

  const loadMore = useCallback(() => {
    const current = generation.current;
    const nextPage = page + 1;
    setLoadingMore(true);
    setLoadMoreFailed(false);
    recordsApi
      .list({ ...listParams(query), page: nextPage, page_size: PAGE_SIZE })
      .then(({ data }) => {
        if (current !== generation.current) return;
        setRecords((prev) => {
          const seen = new Set(prev.map((r) => r.id));
          return [...prev, ...(data.results ?? []).filter((r) => !seen.has(r.id))];
        });
        setPage(nextPage);
        position.current = { key: queryKey, pages: nextPage };
      })
      .catch(() => {
        if (current === generation.current) setLoadMoreFailed(true);
      })
      .finally(() => {
        if (current === generation.current) setLoadingMore(false);
      });
  }, [page, query, queryKey]);

  /* ── Remember where the reader is, for Back and reload ──────────────── */
  useEffect(() => {
    if (loading || restoreScrollTo.current === null) return;
    window.scrollTo(0, restoreScrollTo.current);
    restoreScrollTo.current = null;
  }, [loading]);

  // Saved when the reader leaves -- for a Record (unmount) or by reloading
  // (pagehide) -- with the scroll position as it is at that moment.
  useEffect(() => {
    const save = () => {
      if (position.current) writePosition({ ...position.current, scrollY: window.scrollY });
    };
    window.addEventListener("pagehide", save);
    return () => {
      window.removeEventListener("pagehide", save);
      save();
    };
  }, []);

  const filterOptions = useMemo(
    () => ({
      recordTypes: [{ value: ALL_VALUE, label: "Any type" }, ...recordTypes],
      colleges,
      classifications,
      years: [
        { value: ALL_VALUE, label: "Any year" },
        ...(filters.year !== ALL_VALUE && !years.includes(filters.year) ? [filters.year] : [])
          .concat(years)
          .map((y) => ({ value: y, label: y })),
      ],
      ip: [
        { value: ALL_VALUE, label: "Any" },
        { value: HAS_IP, label: "Has IP" },
        ...Object.entries(IP_TYPE_LABELS).map(([value, label]) => ({ value, label })),
      ],
    }),
    [recordTypes, colleges, classifications, years, filters.year],
  );

  const openPublish = () =>
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set(PUBLISH_PARAM, "new");
      return next;
    });

  const narrowed = activeFilterCount(filters) > 0 || Boolean(activeQuery);

  const clearFilters = () => {
    setSearchInput("");
    updateQuery((current) => ({ ...DEFAULT_QUERY, sort: current.sort }));
  };

  const remaining = totalCount === null ? 0 : totalCount - records.length;

  const research = (
    <>
      {refFailed && (
        <div role="alert" className="mb-3 flex flex-wrap items-center gap-3 text-small text-stone-700">
          Some filters couldn&apos;t load, so their lists may be incomplete.
          <button type="button" onClick={() => setRefAttempt((n) => n + 1)} className={PILL_SECONDARY}>
            Retry filters
          </button>
        </div>
      )}

      <DiscoverFilterBar
        filters={filters}
        onChange={setFilters}
        sort={sort}
        onSort={setSort}
        options={filterOptions}
        loading={refLoading}
        resultCount={loading ? null : totalCount}
      />

      <p aria-live="polite" className="mt-5 mb-3 min-h-[20px] text-small text-stone-600">
        {/* No count over an empty state: its own message already says so. */}
        {loading || !totalCount ? "" : `${totalCount} result${totalCount === 1 ? "" : "s"}`}
      </p>

      {loading ? (
        <ResultsSkeleton />
      ) : failed ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-triangle-exclamation"
          title="We couldn't load research"
          message="Check your connection, then try again."
          action={
            <button type="button" onClick={() => setAttempt((n) => n + 1)} className={PILL_SECONDARY}>
              Try again
            </button>
          }
        />
      ) : records.length === 0 ? (
        narrowed ? (
          <EmptyState
            framed
            icon="fa-filter-circle-xmark"
            title="No research matches these filters"
            message="Try removing a filter or searching for something else."
            action={
              <button type="button" onClick={clearFilters} className={PILL_SECONDARY}>
                Clear filters
              </button>
            }
          />
        ) : (
          <EmptyState
            framed
            icon="fa-book-open"
            title="Nothing has been published yet."
            message="Research appears here once it has been reviewed and published."
            action={
              canPublish ? (
                <button type="button" onClick={openPublish} className={PILL_PRIMARY}>
                  Publish
                </button>
              ) : undefined
            }
          />
        )
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {records.map((record) => (
              <DiscoverResultCard
                key={record.id}
                record={record}
                searchHighlight={activeQuery}
                onCite={() => setCiteRecord(record)}
              />
            ))}
          </div>

          {(remaining > 0 || loadMoreFailed) && (
            <div className="flex flex-col items-center gap-2 mt-8">
              {loadMoreFailed && (
                <p role="alert" className="text-small text-stone-700">
                  More results didn&apos;t load.
                </p>
              )}
              <button type="button" onClick={loadMore} disabled={loadingMore} className={PILL_SECONDARY}>
                {loadingMore && <Spinner size="sm" />}
                {loadingMore ? "Loading…" : loadMoreFailed ? "Try again" : `Load more (${remaining} left)`}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );

  return (
    <div className="min-h-screen bg-canvas flex flex-col">
      {/* Discover paints its own background, so AppShell draws it full-bleed;
          the width is still the app's standard one (IR-521). Its private bar
          (menu button and bell) is gone: the bell is in the sidebar, and
          AppShell's phone bar carries both below `md` (IR-519). */}
      <div className={cn(PAGE_WIDTH.standard, "px-4 sm:px-7 pt-4 sm:pt-7 pb-12 flex-1")}>
        <PageHeader
          title="Discover"
          description="Published theses, research and projects from across CIT-U."
          actions={
            canPublish ? (
              <button type="button" onClick={openPublish} className={PILL_PRIMARY}>
                <i className="fas fa-plus text-[12px]" aria-hidden />
                Publish
              </button>
            ) : undefined
          }
        />

        <DiscoverSearchComposer value={searchInput} onChange={setSearchInput} />

        <DiscoverTabs
          tabs={[{ id: "research", label: "Research", content: research }]}
          active={tab}
          onSelect={setTab}
        />
      </div>

      <PaperCiteModal record={citeRecord} isOpen={Boolean(citeRecord)} onClose={() => setCiteRecord(null)} />
    </div>
  );
}

/** Placeholder cards in the grid's own shape, announced once as loading. */
function ResultsSkeleton() {
  return (
    <div role="status">
      <span className="sr-only">Loading research…</span>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" aria-hidden="true">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="bg-white rounded-xl border border-stone-200 p-card-compact md:p-card">
            <div className="h-3 w-1/3 rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
            <div className="mt-3 h-5 w-5/6 rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
            <div className="mt-2 h-5 w-2/3 rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
            <div className="mt-4 h-3 w-full rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
            <div className="mt-2 h-3 w-11/12 rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
          </div>
        ))}
      </div>
    </div>
  );
}
