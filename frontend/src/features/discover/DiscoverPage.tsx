import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PUBLISH_PARAM } from "@/features/publish/PublishDialog";
import { useRole } from "@/hooks/useRole";
import { canAccess } from "@/lib/access";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import { IP_TYPE_LABELS } from "@/types/records";
import type { RecordListItem } from "@/types/records";
import { ALL_VALUE, type FilterOption } from "./DiscoverFilterDropdown";
import {
  activeFilterCount,
  DiscoverFilterBar,
  EMPTY_FILTERS,
  HAS_IP,
  type DiscoverFilters,
  type DiscoverSort,
} from "./DiscoverFilterBar";
import { DiscoverResultCard } from "./DiscoverResultCard";
import { DiscoverSearchComposer } from "./DiscoverSearchComposer";
import { DiscoverTabs } from "./DiscoverTabs";
import { PaperCiteModal } from "./PaperCiteModal";
import { buildYearOptions } from "./discoverUtils";

const PAGE_SIZE = 12;

const ORDERING: Record<DiscoverSort, string> = {
  newest: "-created_at",
  viewed: "-access_count",
};

/**
 * Discover: find published research, and start a submission (IR-407, F2;
 * spec §4.3).
 *
 * Every control maps to a query param the list endpoint already understands,
 * and filtering is server-side, so a match beyond the first page is never
 * missed. The old saved views are gone: Latest and Most viewed are Sort, IP &
 * Patents and Theses are filters, and "For you" -- which had no personalisation
 * signal to rank on -- is removed rather than kept as a relabelled recency feed.
 */
export default function DiscoverPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
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

  const [searchInput, setSearchInput] = useState(searchParams.get("q") ?? "");
  const [activeQuery, setActiveQuery] = useState(searchParams.get("q") ?? "");

  const [filters, setFilters] = useState<DiscoverFilters>(EMPTY_FILTERS);
  const [sort, setSort] = useState<DiscoverSort>("newest");
  const [tab, setTab] = useState("research");

  const [classifications, setClassifications] = useState<FilterOption[]>([]);
  const [colleges, setColleges] = useState<FilterOption[]>([]);
  const [recordTypes, setRecordTypes] = useState<FilterOption[]>([]);
  const [refLoading, setRefLoading] = useState(true);

  const [citeRecord, setCiteRecord] = useState<RecordListItem | null>(null);
  const [yearPool, setYearPool] = useState<RecordListItem[]>([]);

  /* ── Reference data drives every filter list ────────────────────────── */
  useEffect(() => {
    let cancelled = false;

    Promise.allSettled([recordsApi.classifications(), accountsApi.colleges(), recordsApi.recordTypes()])
      .then(([classRes, collegeRes, typeRes]) => {
        if (cancelled) return;
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
      })
      .finally(() => {
        if (!cancelled) setRefLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  /* ── Debounce the search box into the query + the URL ───────────────── */
  useEffect(() => {
    const handle = setTimeout(() => {
      setActiveQuery(searchInput.trim());
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (searchInput.trim()) next.set("q", searchInput.trim());
          else next.delete("q");
          return next;
        },
        { replace: true },
      );
    }, 300);

    return () => clearTimeout(handle);
    // Re-running on a `setSearchParams` identity change would loop on every
    // URL write; only the typed text should start the debounce.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  /* ── The query the API actually understands ─────────────────────────── */
  const queryParams = useMemo(() => {
    const params: Record<string, unknown> = { page_size: PAGE_SIZE, ordering: ORDERING[sort] };

    if (activeQuery) params.search = activeQuery;
    if (filters.recordType !== ALL_VALUE) params.record_type = filters.recordType;
    if (filters.colleges.length > 0) params.college = filters.colleges.join(",");
    if (filters.classifications.length > 0) params.classification = filters.classifications.join(",");
    if (filters.year !== ALL_VALUE) {
      params.year_from = filters.year;
      params.year_to = filters.year;
    }
    if (filters.ip === HAS_IP) params.is_ip = true;
    else if (filters.ip !== ALL_VALUE) params.ip_type = filters.ip;

    return params;
  }, [sort, activeQuery, filters]);

  /* Guard against a slow early request overwriting a newer one. */
  const requestSeq = useRef(0);

  useEffect(() => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setFailed(false);
    setLoadMoreFailed(false);

    recordsApi
      .list({ ...queryParams, page: 1 })
      .then(({ data }) => {
        if (seq !== requestSeq.current) return;
        const results = data.results ?? [];
        setRecords(results);
        setTotalCount(data.count ?? results.length);
        setPage(1);
        setYearPool((prev) => {
          const seen = new Set(prev.map((r) => r.id));
          const added = results.filter((r) => !seen.has(r.id));
          return added.length > 0 ? [...prev, ...added] : prev;
        });
      })
      .catch(() => {
        if (seq !== requestSeq.current) return;
        setRecords([]);
        setTotalCount(null);
        setFailed(true);
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
  }, [queryParams, attempt]);

  const loadMore = useCallback(() => {
    const nextPage = page + 1;
    setLoadingMore(true);
    setLoadMoreFailed(false);
    recordsApi
      .list({ ...queryParams, page: nextPage })
      .then(({ data }) => {
        setRecords((prev) => [...prev, ...(data.results ?? [])]);
        setPage(nextPage);
      })
      .catch(() => setLoadMoreFailed(true))
      .finally(() => setLoadingMore(false));
  }, [page, queryParams]);

  const filterOptions = useMemo(
    () => ({
      recordTypes: [{ value: ALL_VALUE, label: "Any type" }, ...recordTypes],
      colleges,
      classifications,
      years: [
        { value: ALL_VALUE, label: "Any year" },
        ...buildYearOptions(yearPool).map((y) => ({ value: y, label: y })),
      ],
      ip: [
        { value: ALL_VALUE, label: "Any" },
        { value: HAS_IP, label: "Has IP" },
        ...Object.entries(IP_TYPE_LABELS).map(([value, label]) => ({ value, label })),
      ],
    }),
    [recordTypes, colleges, classifications, yearPool],
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
    setActiveQuery("");
    setFilters(EMPTY_FILTERS);
  };

  const remaining = totalCount === null ? 0 : totalCount - records.length;

  const research = (
    <>
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
    <div className="min-h-screen bg-stone-50 flex flex-col">
      {/* AppShell draws no shared header on "/" until F1 (IR-413) moves
          Discover under it, so this bar carries the drawer toggle and the
          notification bell -- without the bell, Discover would be the one
          screen where new notifications are invisible. */}
      <div className="flex items-center gap-3 px-4 sm:px-7 pt-4">
        <button
          type="button"
          onClick={toggleSidebar}
          className={cn(
            "md:hidden w-10 h-10 shrink-0 rounded-xl border border-stone-200 bg-white flex items-center justify-center text-stone-700",
            FOCUS_RING,
          )}
          aria-label="Toggle navigation"
        >
          <i className="fas fa-bars text-[14px]" aria-hidden />
        </button>
        <div className="ml-auto shrink-0">
          <NotificationBell />
        </div>
      </div>

      <div className="w-full max-w-6xl mx-auto px-4 sm:px-7 pt-2 pb-12 flex-1">
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
