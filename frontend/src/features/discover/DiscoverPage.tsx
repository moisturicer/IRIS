import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { accountsApi } from "@/api/accounts";
import { useUIStore } from "@/store/ui.store";
import { Spinner } from "@/components/ui/Spinner";
import { IP_TYPE_LABELS } from "@/types/records";
import type { RecordListItem } from "@/types/records";
import { DiscoverRecordCard } from "./DiscoverRecordCard";
import { ALL_VALUE, type FilterOption } from "./DiscoverFilterDropdown";
import { DiscoverFilterPanel, EMPTY_FILTERS, type DiscoverFilters } from "./DiscoverFilterPanel";
import { DiscoverSearchComposer } from "./DiscoverSearchComposer";
import { PaperCiteModal } from "./PaperCiteModal";
import { buildYearOptions } from "./discoverUtils";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 12;

/**
 * Saved views. Each maps to a real query.
 *
 * "For you" has no personalisation signal available — `User` carries no college
 * or interest data — so it is the default recency feed. Kept because the agreed
 * design shows it; revisit once the profile exposes something to rank on.
 */
const VIEWS = [
  { id: "for-you", label: "For you", params: { ordering: "-created_at" } },
  { id: "latest", label: "Latest", params: { ordering: "-created_at" } },
  { id: "viewed", label: "Most Viewed", params: { ordering: "-access_count" } },
  { id: "ip", label: "IP & Patents", params: { ordering: "-created_at", is_ip: true } },
] as const;

type ViewId = (typeof VIEWS)[number]["id"] | "theses";

export default function DiscoverPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchInput, setSearchInput] = useState(searchParams.get("q") ?? "");
  const [activeQuery, setActiveQuery] = useState(searchParams.get("q") ?? "");

  const [view, setView] = useState<ViewId>("for-you");
  const [filters, setFilters] = useState<DiscoverFilters>(EMPTY_FILTERS);
  const [filterSignal, setFilterSignal] = useState(0);

  const [classifications, setClassifications] = useState<FilterOption[]>([]);
  const [colleges, setColleges] = useState<FilterOption[]>([]);
  const [recordTypes, setRecordTypes] = useState<FilterOption[]>([]);
  const [refLoading, setRefLoading] = useState(true);

  const [citeRecord, setCiteRecord] = useState<RecordListItem | null>(null);
  const [yearPool, setYearPool] = useState<RecordListItem[]>([]);

  /* ── Reference data drives every filter list ────────────────────────── */
  useEffect(() => {
    let cancelled = false;

    Promise.allSettled([
      recordsApi.classifications(),
      accountsApi.colleges(),
      recordsApi.recordTypes(),
    ])
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
            (typeRes.value.data.results ?? []).map((t) => ({ value: String(t.id), label: t.name })),
          );
        }
      })
      .finally(() => {
        if (!cancelled) setRefLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  /* "Theses" is a real record type, so the tab resolves to its id at runtime. */
  const thesesTypeId = useMemo(
    () => recordTypes.find((t) => /thesis|research/i.test(t.label))?.value ?? null,
    [recordTypes],
  );

  /* ── Debounce the search box into the query + the URL ───────────────── */
  useEffect(() => {
    const handle = setTimeout(() => {
      setActiveQuery(searchInput.trim());
      const next = new URLSearchParams(searchParams);
      if (searchInput.trim()) next.set("q", searchInput.trim());
      else next.delete("q");
      setSearchParams(next, { replace: true });
    }, 300);

    return () => clearTimeout(handle);
    // `searchParams`/`setSearchParams` are intentionally excluded — including
    // them would re-fire this effect on every URL write and loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  /* ── The query the API actually understands ─────────────────────────── */
  const queryParams = useMemo(() => {
    const preset =
      view === "theses"
        ? { ordering: "-created_at", ...(thesesTypeId ? { record_type: thesesTypeId } : {}) }
        : VIEWS.find((v) => v.id === view)!.params;

    const params: Record<string, unknown> = { page_size: PAGE_SIZE, ...preset };

    if (activeQuery) params.search = activeQuery;
    if (filters.topics.length > 0) params.classification = filters.topics.join(",");
    if (filters.colleges.length > 0) params.college = filters.colleges.join(",");
    if (filters.year !== ALL_VALUE) {
      params.year_from = filters.year;
      params.year_to = filters.year;
    }
    if (filters.ipType !== ALL_VALUE) params.ip_type = filters.ipType;
    if (filters.recordType !== ALL_VALUE) params.record_type = filters.recordType;

    return params;
  }, [view, thesesTypeId, activeQuery, filters]);

  /* Guard against a slow early request overwriting a newer one. */
  const requestSeq = useRef(0);

  useEffect(() => {
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);

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
        setTotalCount(0);
        setError("Could not load records. Is the backend running?");
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
  }, [queryParams]);

  const loadMore = useCallback(() => {
    const nextPage = page + 1;
    setLoadingMore(true);
    recordsApi
      .list({ ...queryParams, page: nextPage })
      .then(({ data }) => {
        setRecords((prev) => [...prev, ...(data.results ?? [])]);
        setPage(nextPage);
      })
      .catch(() => setError("Could not load more records."))
      .finally(() => setLoadingMore(false));
  }, [page, queryParams]);

  const yearOptions = useMemo<FilterOption[]>(
    () => [
      { value: ALL_VALUE, label: "Any year" },
      ...buildYearOptions(yearPool).map((y) => ({ value: y, label: y })),
    ],
    [yearPool],
  );

  const ipTypeOptions = useMemo<FilterOption[]>(
    () => [
      { value: ALL_VALUE, label: "Any IP type" },
      ...Object.entries(IP_TYPE_LABELS).map(([value, label]) => ({ value, label })),
    ],
    [],
  );

  const recordTypeOptions = useMemo<FilterOption[]>(
    () => [{ value: ALL_VALUE, label: "Any record type" }, ...recordTypes],
    [recordTypes],
  );

  const activeFilterCount =
    filters.topics.length +
    filters.colleges.length +
    (filters.year !== ALL_VALUE ? 1 : 0) +
    (filters.ipType !== ALL_VALUE ? 1 : 0) +
    (filters.recordType !== ALL_VALUE ? 1 : 0);

  const resetAll = () => {
    setSearchInput("");
    setFilters(EMPTY_FILTERS);
    setView("for-you");
  };

  const tabs: { id: ViewId; label: string }[] = [
    ...VIEWS.map((v) => ({ id: v.id as ViewId, label: v.label })),
    { id: "theses", label: "Theses" },
  ];

  const hasMore = records.length < totalCount;

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col">
      {/* ── Top bar. Spans the full width, unlike the centred record column. ── */}
      <header className="bg-white border-b border-stone-200 px-4 sm:px-7 py-3 flex items-center gap-3">
        <button
          type="button"
          onClick={toggleSidebar}
          className="md:hidden w-9 h-9 shrink-0 rounded-xl border border-stone-200 flex items-center justify-center text-stone-600"
          aria-label="Toggle navigation"
        >
          <i className="fas fa-bars text-sm" />
        </button>

        <span className="w-7 h-7 rounded-full bg-brand text-white flex items-center justify-center shrink-0">
          <i className="fas fa-compass text-[12px]" />
        </span>
        <div className="min-w-0">
          <h1 className="text-[16px] font-bold text-stone-900 leading-tight truncate">
            IRIS Discovery
          </h1>
          <p className="text-[10px] font-bold uppercase tracking-wider text-stone-400 leading-tight">
            Institutional Knowledge Base
          </p>
        </div>
      </header>

      <div className="w-full max-w-5xl mx-auto px-4 sm:px-7 py-5 flex-1 flex flex-col">

        <DiscoverSearchComposer
          value={searchInput}
          onChange={setSearchInput}
          onAddFilter={() => setFilterSignal((n) => n + 1)}
        />

        {/* ── Filter + saved views + result count ───────────────────────── */}
        <div className="flex flex-wrap items-center gap-3 mt-5 mb-4">
          <DiscoverFilterPanel
            filters={filters}
            onChange={setFilters}
            onClear={() => setFilters(EMPTY_FILTERS)}
            activeCount={activeFilterCount}
            topicOptions={classifications}
            collegeOptions={colleges}
            yearOptions={yearOptions}
            ipTypeOptions={ipTypeOptions}
            recordTypeOptions={recordTypeOptions}
            loading={refLoading}
            openSignal={filterSignal}
          />

          <div
            role="tablist"
            aria-label="Saved views"
            className="flex items-center gap-1 p-1 bg-stone-100/80 rounded-full overflow-x-auto"
          >
            {tabs.map((tab) => (
              <button
                key={tab.id}
                role="tab"
                aria-selected={view === tab.id}
                type="button"
                onClick={() => setView(tab.id)}
                className={cn(
                  "px-3.5 py-1.5 rounded-full text-[12px] font-semibold whitespace-nowrap transition-colors",
                  view === tab.id
                    ? "bg-white text-stone-900 shadow-card"
                    : "text-stone-500 hover:text-stone-900",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <span className="ml-auto text-[12px] text-stone-400 font-medium whitespace-nowrap">
            {loading ? "Loading…" : `${totalCount} record${totalCount === 1 ? "" : "s"}`}
          </span>
        </div>

        {/* ── Feed ──────────────────────────────────────────────────────── */}
        {loading ? (
          <div className="py-24 flex flex-col items-center justify-center gap-3">
            <Spinner />
            <span className="text-xs text-stone-400 font-medium">Searching the repository…</span>
          </div>
        ) : error ? (
          <EmptyState icon="fa-triangle-exclamation" tone="error" title="Something went wrong" body={error} />
        ) : records.length === 0 ? (
          <EmptyState
            icon="fa-book-open"
            title="No research papers found"
            body={
              activeFilterCount > 0 || activeQuery
                ? "No records match your current search and filters."
                : "Nothing has been published yet. Records appear here once they clear review."
            }
            action={
              activeFilterCount > 0 || activeQuery
                ? { label: "Reset all filters", onClick: resetAll }
                : undefined
            }
          />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4">
              {records.map((record) => (
                <DiscoverRecordCard
                  key={record.id}
                  record={record}
                  searchHighlight={activeQuery}
                  onCite={() => setCiteRecord(record)}
                />
              ))}
            </div>

            {hasMore && (
              <div className="flex justify-center mt-6">
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="px-5 py-2.5 rounded-full border border-stone-200 bg-white text-stone-700 hover:border-brand hover:text-brand text-xs font-bold transition disabled:opacity-60 flex items-center gap-2"
                >
                  {loadingMore ? <Spinner size="sm" /> : <i className="fas fa-arrow-down text-[10px]" />}
                  <span>{loadingMore ? "Loading…" : `Load more (${totalCount - records.length} left)`}</span>
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <PaperCiteModal
        record={citeRecord}
        isOpen={Boolean(citeRecord)}
        onClose={() => setCiteRecord(null)}
      />
    </div>
  );
}

function EmptyState({
  icon,
  title,
  body,
  action,
  tone = "neutral",
}: {
  icon: string;
  title: string;
  body: string;
  action?: { label: string; onClick: () => void };
  tone?: "neutral" | "error";
}) {
  return (
    <div className="py-16 flex flex-col items-center justify-center text-center bg-white rounded-2xl border border-stone-200 px-6">
      <div
        className={cn(
          "w-12 h-12 rounded-xl flex items-center justify-center mb-3 text-[18px]",
          tone === "error" ? "bg-red-50 text-red-400" : "bg-stone-100 text-stone-400",
        )}
      >
        <i className={cn("fas", icon)} />
      </div>
      <h3 className="text-[15px] font-bold text-stone-900">{title}</h3>
      <p className="text-[13px] text-stone-500 mt-1 max-w-sm">{body}</p>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-4 px-4 py-2 bg-brand hover:bg-brand-light text-white text-[12px] font-bold rounded-lg transition"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
