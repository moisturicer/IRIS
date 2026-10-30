import { errorDetail } from "@/lib/errorDetail";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import { Modal } from "@/components/ui/Modal";
import { PAGE_WIDTH } from "@/components/layout/PageContainer";
import { EmptyState } from "@/components/shared/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { PUBLISH_PARAM } from "@/features/publish/PublishDialog";
import { useRole } from "@/hooks/useRole";
import { canAccess } from "@/lib/access";
import { cn } from "@/lib/utils";
import { IP_TYPE_LABELS } from "@/types/records";
import type { DiscoverInterests, ForYouItem, RecordListItem } from "@/types/records";
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
const COLUMNS_KEY = "iris.discover.columns";

type ColumnCount = 1 | 2 | 3;

function readColumns(): ColumnCount {
  try {
    const saved = localStorage.getItem(COLUMNS_KEY);
    return saved === "2" || saved === "3" ? Number(saved) as ColumnCount : 1;
  } catch {
    return 1;
  }
}

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
 * Both feeds retain catalogue filters. Latest adds search and sort; For you uses its
 * cursor-based recommendation endpoint and carries its explanation per item.
 * The URL holds the feed and catalogue query (`discoverQuery.ts`), so Back,
 * reload and a copied link restore the view, and requests are fenced by it.
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
  const [feedRecords, setFeedRecords] = useState<ForYouItem[]>([]);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [feedNotice, setFeedNotice] = useState("");
  const [interests, setInterests] = useState<DiscoverInterests>({ classifications: [], psced: [] });
  const [interestOptions, setInterestOptions] = useState<DiscoverInterests>({ classifications: [], psced: [] });
  const [interestSelection, setInterestSelection] = useState<{ classification_ids: number[]; psced_ids: number[] }>({ classification_ids: [], psced_ids: [] });
  const [interestOpen, setInterestOpen] = useState(false);
  const [interestLoading, setInterestLoading] = useState(true);
  const [interestLoadFailed, setInterestLoadFailed] = useState<string | null>(null);
  const [interestSaving, setInterestSaving] = useState(false);
  const [interestError, setInterestError] = useState("");
  const [resetConfirming, setResetConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  /** What the reader's last Not interested, Undo or reset did; Undo only for the last dismissal. */
  const [feedback, setFeedback] = useState<{ text: string; undo?: ForYouItem } | null>(null);
  const [feedbackError, setFeedbackError] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [loadMoreFailed, setLoadMoreFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  /* ── The query lives in the URL; this is its one parsed form ────────── */
  const query = useMemo(() => parseDiscoverQuery(searchParams), [searchParams]);
  const queryKey = discoverQueryKey(query);
  const { q: activeQuery, filters, sort } = query;
  const feed = query.feed;
  const feedKey = `${queryKey}|mode=${feed}`;

  const [searchInput, setSearchInput] = useState(query.q);

  /* The box follows the URL when it changes underneath it -- the sidebar's
     Discover link, or Clear filters -- but never while the reader is typing,
     since only a change to `q` itself runs this. */
  useEffect(() => {
    setSearchInput((typed) => (typed.trim() === query.q ? typed : query.q));
  }, [query.q]);

  const [tab, setTab] = useState("research");
  const [columns, setColumns] = useState<ColumnCount>(readColumns);
  const chooseColumns = (value: ColumnCount) => {
    setColumns(value);
    try { localStorage.setItem(COLUMNS_KEY, String(value)); } catch { /* Browsing still works without storage. */ }
  };
  const gridColumns = columns === 1
    ? "grid-cols-1"
    : columns === 2 ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3";
  const nextColumns = (columns === 3 ? 1 : columns + 1) as ColumnCount;

  const [classifications, setClassifications] = useState<FilterOption[]>([]);
  const [colleges, setColleges] = useState<FilterOption[]>([]);
  const [recordTypes, setRecordTypes] = useState<FilterOption[]>([]);
  const [years, setYears] = useState<string[]>([]);
  const [refLoading, setRefLoading] = useState(true);
  const [refFailed, setRefFailed] = useState<string | null>(null);
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
  const setSort = (next: DiscoverSort) => updateQuery((current) => ({ ...current, sort: next, feed: "latest" }));

  useEffect(() => {
    let cancelled = false;
    setRefLoading(true);
    setRefFailed(null);

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
        const failure = [classRes, collegeRes, typeRes, facetRes].find((r) => r.status === "rejected");
        setRefFailed(failure ? errorDetail(failure.reason, "Some filters couldn't load, so their lists may be incomplete.") : null);
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

  useEffect(() => {
    let cancelled = false;
    Promise.all([recordsApi.interests(), recordsApi.classifications(), recordsApi.pscedList()])
      .then(([saved, classes, psced]) => {
        if (cancelled) return;
        setInterests(saved.data);
        setInterestSelection({
          classification_ids: saved.data.classifications.map((x) => x.id),
          psced_ids: saved.data.psced.map((x) => x.id),
        });
        setInterestOptions({
          classifications: classes.data.results ?? [],
          psced: psced.data.results ?? [],
        });
      })
      .catch((error: unknown) => { if (!cancelled) setInterestLoadFailed(errorDetail(error, "Areas couldn’t load. You can still browse Latest; try setting them again later.")); })
      .finally(() => { if (!cancelled) setInterestLoading(false); });
    return () => { cancelled = true; };
  }, []);

  /* ── Debounce the search box into the query + the URL ───────────────── */
  useEffect(() => {
    const handle = setTimeout(() => {
      updateQuery((current) => {
        const q = searchInput.trim();
        return q === current.q ? current : { ...current, q, feed: "latest" };
      });
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
  /** Dismissals not yet confirmed by the server, each resolving to whether it was
   *  stored. A page requested meanwhile may still carry the Record (IR-576). */
  const pendingDismissals = useRef(new Map<number, Promise<boolean>>());
  const withoutHidden = (rows: ForYouItem[]) => rows.filter((r) => !pendingDismissals.current.has(r.id));
  const restoreScrollTo = useRef<number | null>(null);
  /** Where the reader is, set only once this query's results are on screen:
   *  until then there is nothing of this query to return to. */
  const position = useRef<Omit<Position, "scrollY"> | null>(null);

  useEffect(() => {
    const current = ++generation.current;
    position.current = null;
    const restored = feed !== "for_you" ? readPosition(queryKey) : null;
    const pages = Math.min(Math.max(restored?.pages ?? 1, 1), MAX_RESTORED_PAGES);
    // A depth past the cap comes back shorter, so its scroll offset would land
    // somewhere the reader never was; start at the top instead.
    restoreScrollTo.current = restored && restored.pages <= MAX_RESTORED_PAGES ? restored.scrollY : null;

    setLoading(true);
    setFailed(null);
    setLoadingMore(false);
    setLoadMoreFailed(null);
    setNextCursor(null);

    (feed === "for_you"
      ? recordsApi.forYou(undefined, listParams(query))
      : recordsApi.list({ ...listParams(query), page: 1, page_size: PAGE_SIZE * pages }))
      .then(({ data }) => {
        if (current !== generation.current) return;
        if (feed === "for_you") {
          const response = data as Awaited<ReturnType<typeof recordsApi.forYou>>["data"];
          setFeedRecords(withoutHidden(response.results ?? []));
          setNextCursor(response.next_cursor);
          setTotalCount(response.count ?? response.results.length);
          if (response.mode === "latest") {
            setFeedNotice("Choose an Area to get recommendations. Showing the latest research for now.");
          } else {
            setFeedNotice((notice) => notice.startsWith("This recommendation list changed") ? notice : "");
          }
          position.current = { key: feedKey, pages: 1 };
          return;
        }
        const list = data as Awaited<ReturnType<typeof recordsApi.list>>["data"];
        const results = list.results ?? [];
        setRecords(results);
        setFeedRecords([]);
        setTotalCount(list.count ?? results.length);
        // Whole pages only: if the server returned fewer rows than asked, the
        // next Load more re-reads the partial page and duplicates are dropped.
        const loaded = Math.max(1, Math.floor(results.length / PAGE_SIZE));
        setPage(loaded);
        position.current = { key: queryKey, pages: loaded };
      })
      .catch((error: unknown) => {
        if (current !== generation.current) return;
        setRecords([]);
        setTotalCount(null);
        setFailed(errorDetail(error, "Check your connection, then try again."));
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
    // `query` is fully described by `feedKey`; keying on the string keeps an
    // unrelated URL change (the Publish dialog) from refetching.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feedKey, attempt]);

  const loadMore = useCallback(() => {
    const current = generation.current;
    const nextPage = page + 1;
    const loadingFeed = feed === "for_you";
    setLoadingMore(true);
    setLoadMoreFailed(null);
    (loadingFeed
      ? recordsApi.forYou(nextCursor ?? undefined, listParams(query))
      : recordsApi.list({ ...listParams(query), page: nextPage, page_size: PAGE_SIZE }))
      .then(({ data }) => {
        if (current !== generation.current) return;
        if (loadingFeed) {
          const response = data as Awaited<ReturnType<typeof recordsApi.forYou>>["data"];
          setFeedRecords((prev) => {
            const seen = new Set(prev.map((r) => r.id));
            return [...prev, ...withoutHidden(response.results ?? []).filter((r) => !seen.has(r.id))];
          });
          setNextCursor(response.next_cursor);
          setTotalCount(response.count);
          return;
        }
        const list = data as Awaited<ReturnType<typeof recordsApi.list>>["data"];
        setRecords((prev) => {
          const seen = new Set(prev.map((r) => r.id));
          return [...prev, ...(list.results ?? []).filter((r) => !seen.has(r.id))];
        });
        setPage(nextPage);
        position.current = { key: queryKey, pages: nextPage };
      })
      .catch((error: unknown) => {
        if (current !== generation.current) return;
        const response = (error as { response?: { status?: number; data?: { code?: string } } }).response;
        if (loadingFeed && (response?.status === 409 || response?.data?.code === "stale_cursor")) {
          setFeedNotice("This recommendation list changed. Refreshing it now.");
          setNextCursor(null);
          setAttempt((n) => n + 1);
        } else setLoadMoreFailed(errorDetail(error, "More results didn't load."));
      })
      .finally(() => {
        if (current === generation.current) setLoadingMore(false);
      });
  }, [page, query, queryKey, feed, nextCursor]);

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
    updateQuery((current) => ({ ...DEFAULT_QUERY, sort: current.sort, feed: current.feed }));
  };

  const remaining = totalCount === null ? 0 : totalCount - records.length;
  const shownRecords: (RecordListItem & { reason?: ForYouItem["reason"] })[] = feed === "for_you" ? feedRecords : records;
  const shownRemaining = feed === "for_you" ? (nextCursor ? Math.max(1, (totalCount ?? 0) - feedRecords.length) : 0) : remaining;

  /* ── Not interested, Undo and reset (IR-576) ─────────────────────────── */
  const report = (text: string, undo?: ForYouItem) => {
    setFeedbackError("");
    setFeedback({ text, undo });
  };
  const adjustCount = (by: number) => setTotalCount((n) => (n === null ? n : n + by));

  // Removed at once; the server keeps the reader's next pages valid without it.
  const notInterested = (record: ForYouItem) => {
    const index = feedRecords.findIndex((r) => r.id === record.id);
    if (index < 0) return;
    const shownIn = generation.current;
    setFeedRecords((prev) => prev.filter((r) => r.id !== record.id));
    adjustCount(-1);
    report(`“${record.title}” won’t be recommended to you again.`, record);
    const stored = recordsApi.notInterested(record.id).then(() => true, (error: unknown) => {
      // Put it back only into the list it left; a reloaded feed already has the truth.
      if (shownIn === generation.current) {
        setFeedRecords((prev) => prev.some((r) => r.id === record.id)
          ? prev
          : [...prev.slice(0, index), record, ...prev.slice(index)]);
        adjustCount(1);
      }
      setFeedback((current) => (current?.undo?.id === record.id ? null : current));
      setFeedbackError(errorDetail(error, "That recommendation couldn’t be hidden. Please try again."));
      return false;
    }).finally(() => pendingDismissals.current.delete(record.id));
    pendingDismissals.current.set(record.id, stored);
  };

  // Undo restores it under a fresh feed, so the list is reloaded rather than patched.
  // It waits for the dismissal itself, or a fast Undo could land before it.
  const undoNotInterested = async (record: ForYouItem) => {
    setFeedbackError("");
    if (!(await (pendingDismissals.current.get(record.id) ?? true))) return;
    try {
      await recordsApi.undoNotInterested(record.id);
      report(`“${record.title}” is back in For you.`);
      setAttempt((n) => n + 1);
    } catch (error) {
      setFeedbackError(errorDetail(error, "Undo didn’t go through. Please try again."));
    }
  };

  const resetInterests = async () => {
    setResetting(true);
    setInterestError("");
    try {
      const { data } = await recordsApi.resetInterests();
      setInterests(data);
      setInterestSelection({ classification_ids: [], psced_ids: [] });
      setInterestOpen(false);
      setResetConfirming(false);
      report("Your interests were reset. Your saved papers and folders are unchanged.");
      if (feed === "for_you") setAttempt((n) => n + 1);
    } catch (error) {
      setInterestError(errorDetail(error, "Your interests couldn’t be reset. Please try again."));
    } finally {
      setResetting(false);
    }
  };

  const saveInterests = async () => {
    setInterestSaving(true);
    setInterestError("");
    try {
      const { data } = await recordsApi.updateInterests(interestSelection);
      setInterests(data);
      setInterestSelection({ classification_ids: data.classifications.map((x) => x.id), psced_ids: data.psced.map((x) => x.id) });
      setInterestOpen(false);
      setFeedNotice("");
      updateQuery((current) => ({ ...current, feed: "for_you" }));
      if (feed === "for_you") setAttempt((n) => n + 1);
    } catch (error) {
      setInterestError(errorDetail(error, "Your Areas couldn’t be saved. Please try again."));
    } finally {
      setInterestSaving(false);
    }
  };

  const research = (
    <>
      <div className="mt-4 flex flex-wrap items-center gap-1.5 sm:gap-2">
        <div role="group" aria-label="Discover feed" className="inline-flex h-11 shrink-0 items-center rounded-lg border border-stone-200 bg-stone-100 p-0.5 shadow-[inset_0_1px_2px_rgb(41_37_36/0.12)]">
          {([["for_you", "For you"], ["latest", "Latest"], ["trending", "Trending"]] as const).map(([value, label]) => (
            <button key={value} type="button" aria-pressed={feed === value}
              title={value === "trending" ? "Most viewed research" : undefined}
              onClick={() => {
                setFeedNotice("");
                setFeedback(null);
                setFeedbackError("");
                updateQuery((current) => ({ ...current, feed: value, q: value === "for_you" ? "" : current.q }));
                if (value === "for_you") setSearchInput("");
              }}
               className={cn("h-full rounded-md px-1.5 text-[11px] sm:px-3 sm:text-small font-semibold", COLOUR_TRANSITION, FOCUS_RING, feed === value ? "bg-brand text-white shadow-sm" : "text-stone-700 hover:bg-surface")}>{label}</button>
          ))}
        </div>
        <button type="button" onClick={() => setInterestOpen(true)}
          aria-label={interests.classifications.length || interests.psced.length ? "Edit Areas" : "Choose Areas"}
          className={cn("inline-flex h-11 w-11 sm:w-auto items-center justify-center gap-1.5 rounded-lg border border-stone-300 bg-white sm:px-3 text-small font-medium text-stone-700 hover:border-stone-400 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}>
          <i className="fas fa-compass text-[12px]" aria-hidden />
          <span className="hidden sm:inline">Areas</span>
        </button>
        <button type="button" onClick={() => chooseColumns(nextColumns)}
          aria-label={`${columns} ${columns === 1 ? "column" : "columns"}; switch to ${nextColumns}`}
          title={`${columns} ${columns === 1 ? "column" : "columns"}; switch to ${nextColumns}`}
          className={cn("ml-auto hidden xl:inline-flex h-11 w-11 items-center justify-center rounded-lg border border-stone-300 bg-white text-stone-700 hover:border-stone-400 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}>
          <svg aria-hidden="true" viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <rect x="1.75" y="2.75" width="12.5" height="10.5" rx="2" />
            {columns === 2 && <path d="M8 2.75v10.5" />}
            {columns === 3 && <path d="M5.92 2.75v10.5M10.08 2.75v10.5" />}
          </svg>
        </button>
        <DiscoverFilterBar
          className="max-xl:ml-auto"
          filters={filters}
          onChange={setFilters}
          showSort={feed === "latest"}
          sort={sort}
          onSort={setSort}
          options={filterOptions}
          loading={refLoading}
          resultCount={loading ? null : totalCount}
        />
        {canPublish && (
          <button type="button" onClick={openPublish} aria-label="Publish"
            className={cn(PILL_PRIMARY, FOCUS_RING, "h-11 w-11 !px-0 sm:w-auto sm:!px-5")}>
            <i className="fas fa-plus text-[12px]" aria-hidden />
            <span className="hidden sm:inline">Publish</span>
          </button>
        )}
      </div>
      {feedNotice && <p role="status" className="mt-3 text-small text-stone-700">{feedNotice}</p>}
      {feed === "for_you" && feedback && (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-small text-stone-700">
          <p role="status">{feedback.text}</p>
          {feedback.undo && (
            <button type="button" onClick={() => void undoNotInterested(feedback.undo!)}
              className={cn("font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
              Undo
            </button>
          )}
        </div>
      )}
      {feed === "for_you" && feedbackError && <p role="alert" className="mt-3 text-small text-brand">{feedbackError}</p>}
      {refFailed && (
        <div role="alert" className="mb-3 flex flex-wrap items-center gap-3 text-small text-stone-700">
          {refFailed}
          <button type="button" onClick={() => setRefAttempt((n) => n + 1)} className={cn(PILL_SECONDARY, FOCUS_RING)}>
            Retry filters
          </button>
        </div>
      )}

      <p aria-live="polite" className="sr-only">
        {/* No count over an empty state: its own message already says so. */}
        {loading || !totalCount ? "" : `${totalCount} result${totalCount === 1 ? "" : "s"}`}
      </p>

      <div className="mt-4">
      {loading ? (
        <ResultsSkeleton columns={gridColumns} />
      ) : failed ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-triangle-exclamation"
          title="We couldn't load research"
          message={failed}
          action={
            <button type="button" onClick={() => setAttempt((n) => n + 1)} className={cn(PILL_SECONDARY, FOCUS_RING)}>
              Try again
            </button>
          }
        />
      ) : shownRecords.length === 0 ? (
        narrowed ? (
          <EmptyState
            framed
            icon="fa-filter-circle-xmark"
            title="No research matches these filters"
            message="Try removing a filter or searching for something else."
            action={
              <button type="button" onClick={clearFilters} className={cn(PILL_SECONDARY, FOCUS_RING)}>
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
                <button type="button" onClick={openPublish} className={cn(PILL_PRIMARY, FOCUS_RING)}>
                  Publish
                </button>
              ) : undefined
            }
          />
        )
      ) : (
        <>
          <div className={cn("grid gap-4", gridColumns)}>
            {shownRecords.map((record) => (
              <DiscoverResultCard
                key={record.id}
                record={record}
                reason={record.reason}
                expanded={columns === 1}
                searchHighlight={activeQuery}
                onCite={() => setCiteRecord(record)}
                onNotInterested={feed === "for_you" ? () => notInterested(record as ForYouItem) : undefined}
              />
            ))}
          </div>

          {(shownRemaining > 0 || loadMoreFailed) && (
            <div className="flex flex-col items-center gap-2 mt-8">
              {loadMoreFailed && (
                <p role="alert" className="text-small text-stone-700">
                  {loadMoreFailed}
                </p>
              )}
              <button type="button" onClick={loadMore} disabled={loadingMore} className={cn(PILL_SECONDARY, FOCUS_RING)}>
                {loadingMore && <Spinner size="sm" />}
                {loadingMore ? "Loading…" : loadMoreFailed ? "Try again" : `Load more (${shownRemaining} left)`}
              </button>
            </div>
          )}
        </>
      )}
      </div>
    </>
  );

  return (
    <div className="min-h-screen bg-surface flex flex-col">
      {/* Discover paints its own background, so AppShell draws it full-bleed;
          the width is still the app's standard one (IR-521). Its private bar
          (menu button and bell) is gone: the bell is in the sidebar, and
          AppShell's phone bar carries both below `md` (IR-519). */}
      <div className={cn(PAGE_WIDTH.standard, "px-4 sm:px-7 pt-4 sm:pt-7 pb-12 flex-1")}>
        <DiscoverSearchComposer value={searchInput} onChange={setSearchInput} />

        <div className="mt-4 flex flex-wrap items-baseline gap-x-4 gap-y-0.5">
          <h1 className="font-display font-semibold text-title sm:text-display text-stone-900">Discover</h1>
          <p className="text-body text-stone-600">Research, projects and reference papers in IRIS.</p>
        </div>

        <DiscoverTabs
          tabs={[{ id: "research", label: "Research", content: research }]}
          active={tab}
          onSelect={setTab}
        />
      </div>

      <Modal open={interestOpen} onClose={() => { setInterestOpen(false); setResetConfirming(false); }} title="Choose Areas for your recommendations" sheet
        footer={<div className="flex items-center justify-between gap-3">
          <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} onClick={() => setInterestSelection({ classification_ids: [], psced_ids: [] })}>Clear Areas</button>
          <button type="button" className={cn(PILL_PRIMARY, FOCUS_RING)} disabled={interestSaving || interestLoading || Boolean(interestLoadFailed)} onClick={() => void saveInterests()}>{interestLoading ? "Loading…" : interestSaving ? "Saving…" : "Save Areas"}</button>
        </div>}>
        <div className="space-y-5 p-5">
          <p className="text-small text-stone-600">Choose any Areas you’d like to see more often. Leave this blank to browse the latest research.</p>
          {interestLoadFailed && <p role="alert" className="text-small text-brand">{interestLoadFailed}</p>}
          {interestError && <p role="alert" className="text-small text-brand">{interestError}</p>}
          <InterestChoices title="Research classifications" options={interestOptions.classifications} selected={interestSelection.classification_ids} onChange={(ids) => setInterestSelection((v) => ({ ...v, classification_ids: ids }))} />
          <InterestChoices title="PSCED areas" options={interestOptions.psced} selected={interestSelection.psced_ids} onChange={(ids) => setInterestSelection((v) => ({ ...v, psced_ids: ids }))} />
          <div className="border-t border-stone-200 pt-4">
            <p className="text-small text-stone-600">Resetting clears your Areas and everything you marked Not interested. Your saved papers and folders stay.</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {resetConfirming ? <>
                <button type="button" className={cn(PILL_PRIMARY, FOCUS_RING)} disabled={resetting} onClick={() => void resetInterests()}>{resetting ? "Resetting…" : "Reset"}</button>
                <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} disabled={resetting} onClick={() => setResetConfirming(false)}>Keep my interests</button>
              </> : (
                <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} onClick={() => setResetConfirming(true)}>Reset my interests</button>
              )}
            </div>
          </div>
        </div>
      </Modal>
      <PaperCiteModal record={citeRecord} isOpen={Boolean(citeRecord)} onClose={() => setCiteRecord(null)} />
    </div>
  );
}

function InterestChoices({ title, options, selected, onChange }: {
  title: string;
  options: { id: number; name: string }[];
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  return <fieldset>
    <legend className="text-small font-semibold text-stone-800">{title}</legend>
    {options.length ? <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
      {options.map((option) => {
        const checked = selected.includes(option.id);
        return <label key={option.id} className="flex items-start gap-2 rounded-lg border border-stone-200 p-2.5 text-small text-stone-700">
          <input type="checkbox" checked={checked} onChange={() => onChange(checked ? selected.filter((id) => id !== option.id) : [...selected, option.id])} className={cn("mt-0.5 accent-brand", FOCUS_RING)} />
          <span>{option.name}</span>
        </label>;
      })}
    </div> : <p className="mt-2 text-small text-stone-500">No Areas available.</p>}
  </fieldset>;
}

/** Placeholder cards in the grid's own shape, announced once as loading. */
function ResultsSkeleton({ columns }: { columns: string }) {
  return (
    <div role="status">
      <span className="sr-only">Loading research…</span>
      <div className={cn("grid gap-4", columns)} aria-hidden="true">
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
