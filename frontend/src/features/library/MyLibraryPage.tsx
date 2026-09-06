import { useCallback, useEffect, useMemo, useState } from "react";
import { recordsApi } from "@/api/records";
import type { RecordListItem } from "@/types/records";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import {
  addCollection,
  clearReadingHistory,
  deleteCollection,
  getCollections,
  getReadingHistory,
  getStarredIds,
  removeFromAllCollections,
  renameCollection,
  toggleStarred,
  type Collection,
  type ReadingVisit,
} from "@/lib/recordLibrary";
import { LibraryFolderRail, isSameView, type LibraryView } from "./LibraryFolderRail";
import { LibraryRecordTable, type LibraryLayout } from "./LibraryRecordTable";
import { cn } from "@/lib/utils";

type SortKey = "added" | "title" | "year";

const SORT_LABELS: Record<SortKey, string> = {
  added: "Date added",
  title: "Title A–Z",
  year: "Year published",
};

/** The list endpoint caps `page_size` at 100, so large folders resolve in chunks. */
const ID_CHUNK = 100;

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/**
 * My Library — the research this reader saved, plus what they liked and read.
 *
 * Everything on this page is stored in **this browser**: IRIS has no
 * server-side bookmark, folder, like or reading-history model, so nothing here
 * syncs between devices and the page says so rather than implying an account
 * library. See `lib/recordLibrary`.
 *
 * The saved ids are resolved through the *list* endpoint (`?id=1,2,3`), which
 * applies `publicly_visible()`. The detail route deliberately is not used:
 * `RecordViewSet.get_queryset` filters only on `list`, so resolving ids one by
 * one would turn a stale localStorage id into a way to read a record the
 * viewer is not allowed to see. Ids the predicate drops are reported as no
 * longer available instead of being silently hidden.
 */
export default function MyLibraryPage() {
  const [collections, setCollections] = useState<Collection[]>(() => getCollections());
  const [starredIds, setStarredIds] = useState<number[]>(() => getStarredIds());
  const [history, setHistory] = useState<ReadingVisit[]>(() => getReadingHistory());

  const [view, setView] = useState<LibraryView>({ kind: "folder", id: "want-to-read" });
  const [layout, setLayout] = useState<LibraryLayout>("list");
  const [sort, setSort] = useState<SortKey>("added");
  const [query, setQuery] = useState("");
  // Below lg the rail stacks *above* the list, so leaving it open would push
  // the papers — the reason for the page — off the first screen.
  const [railOpen, setRailOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth >= 1024,
  );

  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [citing, setCiting] = useState<RecordListItem | null>(null);
  const [disclosureCount, setDisclosureCount] = useState<number | null>(null);

  /* The ids this view is asking for, in the order the library stores them. */
  const viewIds = useMemo<number[]>(() => {
    if (view.kind === "starred") return [...starredIds].reverse();
    if (view.kind === "history") return history.map((v) => v.recordId);
    const folder = collections.find((c) => c.id === view.id);
    return folder ? [...folder.recordIds].reverse() : [];
  }, [view, collections, starredIds, history]);

  const viewTitle = useMemo(() => {
    if (view.kind === "starred") return "Liked Papers";
    if (view.kind === "history") return "Reading History";
    return collections.find((c) => c.id === view.id)?.name ?? "Folder";
  }, [view, collections]);

  const load = useCallback(async () => {
    if (viewIds.length === 0) {
      setRecords([]);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    try {
      const pages = await Promise.all(
        chunk(viewIds, ID_CHUNK).map((ids) =>
          recordsApi.list({ id: ids.join(","), page_size: ID_CHUNK }),
        ),
      );
      setRecords(pages.flatMap((p) => p.data.results ?? []));
    } catch {
      setFailed(true);
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [viewIds]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setSelected(new Set());
  }, [view]);

  useEffect(() => {
    recordsApi
      .mine()
      .then(({ data }) => {
        const list = Array.isArray(data)
          ? data
          : ((data as unknown as { results?: RecordListItem[] }).results ?? []);
        setDisclosureCount(list.length);
      })
      .catch(() => setDisclosureCount(null));
  }, []);

  /* Ordering and filtering happen over the resolved records, in view order. */
  const visible = useMemo(() => {
    const order = new Map(viewIds.map((id, i) => [id, i]));
    const needle = query.trim().toLowerCase();

    const matched = needle
      ? records.filter(
          (r) =>
            r.title.toLowerCase().includes(needle) ||
            (r.authors ?? []).some((a) =>
              (typeof a === "string" ? a : a?.name ?? "").toLowerCase().includes(needle),
            ),
        )
      : records;

    const sorted = [...matched];
    if (sort === "title") sorted.sort((a, b) => a.title.localeCompare(b.title));
    else if (sort === "year")
      sorted.sort((a, b) => (b.year_accomplished ?? 0) - (a.year_accomplished ?? 0));
    else sorted.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));

    return sorted;
  }, [records, viewIds, query, sort]);

  const viewedAt = useMemo(
    () => Object.fromEntries(history.map((v) => [v.recordId, v.viewedAt])),
    [history],
  );

  /** Saved, but the visibility predicate no longer returns them. */
  const unavailable = viewIds.length - records.length;

  const toggleSelect = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleAll = () =>
    setSelected((prev) =>
      prev.size === visible.length ? new Set() : new Set(visible.map((r) => r.id)),
    );

  const handleToggleStar = (id: number) => {
    toggleStarred(id);
    setStarredIds(getStarredIds());
  };

  const handleRemove = (ids: number[]) => {
    if (view.kind === "starred") {
      ids.forEach((id) => toggleStarred(id));
      setStarredIds(getStarredIds());
    } else {
      setCollections(removeFromAllCollections(collections, ids));
    }
    setSelected(new Set());
  };

  const emptyCopy = (): { title: string; message: string } => {
    if (view.kind === "starred")
      return {
        title: "No liked papers yet",
        message: "Tap the star on any record to keep it here.",
      };
    if (view.kind === "history")
      return {
        title: "No reading history yet",
        message: "Papers you open will be listed here, newest first.",
      };
    return {
      title: `Nothing in ${viewTitle} yet`,
      message: "Save a paper from Discover or a record page to file it here.",
    };
  };

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div>
          <h1 className="text-[20px] font-bold text-stone-900 flex items-center gap-2">
            <i className="fas fa-bookmark text-[15px] text-brand" aria-hidden />
            My Library
          </h1>
          <p className="text-[13px] text-stone-500 mt-1">
            Saved research, likes and folders — stored in this browser only.
          </p>
        </div>
      </div>

      <div className="lg:flex lg:gap-5 lg:items-start">
        {railOpen ? (
          <div className="mb-4 lg:mb-0 lg:w-64 lg:shrink-0 lg:sticky lg:top-6 lg:h-[calc(100vh-8rem)]">
            <LibraryFolderRail
              collections={collections}
              view={view}
              onViewChange={setView}
              onCreate={(name) => setCollections(addCollection(collections, name))}
              onRename={(id, name) => setCollections(renameCollection(collections, id, name))}
              onDelete={(id) => {
                setCollections(deleteCollection(collections, id));
                if (isSameView(view, { kind: "folder", id }))
                  setView({ kind: "folder", id: "want-to-read" });
              }}
              starredCount={starredIds.length}
              historyCount={history.length}
              disclosureCount={disclosureCount}
              onCollapse={() => setRailOpen(false)}
            />
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setRailOpen(true)}
            className="mb-4 lg:mb-0 lg:shrink-0 flex items-center gap-2 px-3 py-2 bg-white border border-stone-200 rounded-xl text-[13px] font-semibold text-stone-600 hover:border-stone-300"
          >
            <i className="fas fa-angles-right text-[12px] text-stone-400" aria-hidden />
            Folders
            <span className="text-stone-400 font-medium truncate max-w-[10rem]">{viewTitle}</span>
          </button>
        )}

        <div className="min-w-0 lg:flex-1">
          {/* Toolbar */}
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <div className="relative flex-1 min-w-[12rem]">
              <i className="fas fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-[12px] text-stone-400" aria-hidden />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search all bookmarks and research…"
                aria-label="Search your library"
                className="w-full pl-9 pr-3 py-2 bg-white border border-stone-200 rounded-xl text-[13px] outline-none focus:border-brand/40 placeholder-stone-400"
              />
            </div>

            <label className="flex items-center gap-1.5 text-[12px] text-stone-500">
              Sort
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as SortKey)}
                className="bg-white border border-stone-200 rounded-lg px-2 py-1.5 text-[12px] text-stone-700 outline-none focus:border-brand/40"
              >
                {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => (
                  <option key={key} value={key}>
                    {SORT_LABELS[key]}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex items-center bg-white border border-stone-200 rounded-lg p-0.5">
              {(["list", "grid"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setLayout(mode)}
                  aria-label={`${mode} view`}
                  aria-pressed={layout === mode}
                  className={cn(
                    "px-2 py-1 rounded-md transition-colors",
                    layout === mode ? "bg-brand-50 text-brand" : "text-stone-400 hover:text-stone-600",
                  )}
                >
                  <i className={cn("fas", mode === "list" ? "fa-list" : "fa-table-cells-large", "text-[12px]")} aria-hidden />
                </button>
              ))}
            </div>
          </div>

          {/* Section heading */}
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 className="text-[15px] font-bold text-stone-900">
              {viewTitle}
              <span className="ml-2 text-[12px] font-medium text-stone-400">
                {loading ? "loading…" : `${visible.length} record${visible.length === 1 ? "" : "s"}`}
              </span>
            </h2>

            {view.kind === "history" && history.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  clearReadingHistory();
                  setHistory([]);
                }}
                className="text-[12px] font-semibold text-stone-500 hover:text-brand"
              >
                Clear history
              </button>
            )}
          </div>

          {/* Bulk bar — only appears once a selection exists */}
          {selected.size > 0 && (
            <div className="flex flex-wrap items-center gap-2 mb-3 px-3 py-2 bg-brand-50 border border-brand-200 rounded-xl">
              <span className="text-[12px] font-semibold text-brand">
                {selected.size} selected
              </span>
              <button
                type="button"
                onClick={() => handleRemove([...selected])}
                className="ml-auto px-2.5 py-1 rounded-lg bg-white border border-brand-200 text-[12px] font-semibold text-brand hover:bg-brand-50"
              >
                {view.kind === "starred" ? "Unlike" : "Remove from library"}
              </button>
              <button
                type="button"
                onClick={() => setSelected(new Set())}
                className="px-2.5 py-1 rounded-lg text-[12px] font-semibold text-stone-500 hover:text-stone-700"
              >
                Clear
              </button>
            </div>
          )}

          {unavailable > 0 && !loading && !failed && (
            <p className="mb-3 px-3 py-2 bg-amber-50 border border-amber-200 rounded-xl text-[12px] text-amber-800">
              <i className="fas fa-eye-slash mr-1.5" aria-hidden />
              {unavailable} saved {unavailable === 1 ? "record is" : "records are"} no longer
              available to you — {unavailable === 1 ? "it may have" : "they may have"} been
              unpublished or withdrawn.
            </p>
          )}

          {/* Body */}
          {loading ? (
            <div className="bg-white border border-stone-200 rounded-2xl divide-y divide-stone-100">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3.5 animate-pulse">
                  <div className="h-3.5 w-3.5 rounded bg-stone-100 shrink-0" />
                  <div className="h-3 rounded bg-stone-100 flex-1" />
                  <div className="h-3 w-32 rounded bg-stone-100 hidden md:block" />
                  <div className="h-3 w-10 rounded bg-stone-100 hidden md:block" />
                </div>
              ))}
            </div>
          ) : failed ? (
            <div className="bg-white border border-stone-200 rounded-2xl p-8 text-center">
              <i className="fas fa-plug-circle-xmark text-[22px] text-stone-300 mb-3" aria-hidden />
              <p className="text-[14px] font-semibold text-stone-700">Could not load your library</p>
              <p className="text-[12px] text-stone-500 mt-1">
                Your saved records are still stored in this browser — only fetching them failed.
              </p>
              <button
                type="button"
                onClick={() => void load()}
                className="mt-3 text-[12px] font-semibold text-brand hover:underline"
              >
                Try again
              </button>
            </div>
          ) : visible.length === 0 ? (
            <div className="bg-white border border-stone-200 rounded-2xl p-10 text-center">
              <i
                className={cn(
                  "fas text-[22px] text-stone-300 mb-3",
                  query ? "fa-magnifying-glass" : "fa-folder-open",
                )} aria-hidden />
              <p className="text-[14px] font-semibold text-stone-700">
                {query ? "No matches in this folder" : emptyCopy().title}
              </p>
              <p className="text-[12px] text-stone-500 mt-1">
                {query ? "Try a different title or author." : emptyCopy().message}
              </p>
            </div>
          ) : (
            <LibraryRecordTable
              records={visible}
              layout={layout}
              query={query}
              selected={selected}
              onToggleSelect={toggleSelect}
              onToggleAll={toggleAll}
              starred={new Set(starredIds)}
              onToggleStar={handleToggleStar}
              onCite={setCiting}
              onRemove={(id) => handleRemove([id])}
              viewedAt={view.kind === "history" ? viewedAt : undefined}
            />
          )}
        </div>
      </div>

      <PaperCiteModal record={citing} isOpen={citing !== null} onClose={() => setCiting(null)} />
    </div>
  );
}
