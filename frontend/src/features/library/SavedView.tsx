import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { recordsApi } from "@/api/records";
import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { isRequestTimeout } from "@/api/requestPolicy";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { Select } from "@/components/ui/Select";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import type { Collection, ReadingVisit } from "@/lib/recordLibrary";
import { readingStatusLabel, sortedItems, type LibraryItem } from "@/store/library.store";
import { cn } from "@/lib/utils";
import type { RecordListItem } from "@/types/records";

import { LibraryRecordTable, type LibraryLayout } from "./LibraryRecordTable";
import type { LibraryView } from "./ReadingPanel";
import { SearchGlyph } from "@/components/brand/IrisBrand";

type SortKey = "added" | "title" | "year";

const SORT_LABELS: Record<SortKey, string> = {
  added: "Date added",
  title: "Title A–Z",
  year:  "Year published",
};

/** The list endpoint caps `page_size` at 100, so large folders resolve in chunks. */
const ID_CHUNK = 100;

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

interface SavedViewProps {
  view:        Exclude<LibraryView, { kind: "research" }>;
  collections: Collection[];
  history:     ReadingVisit[];
  /** The account's saves (IR-566), keyed by Record id. */
  library:     Record<number, LibraryItem>;
  libraryLoad: "idle" | "loading" | "ready" | "error";
  /** `libraryLoad` is `error` because the read timed out (IR-906). */
  libraryInterrupted?: boolean;
  onRetryLibrary: () => void;
  onRemove:    (ids: number[]) => void;
  onRename:    (id: string, name: string) => void;
  onDelete:    (id: string) => void;
  onClearHistory: () => void;
  /** The Reading status filters, set under the search in the toolbar. */
  filters?:       ReactNode;
  /** The Folder picker, set beside Sort in the toolbar. */
  folderControl?: ReactNode;
}

/**
 * One view of the reader's saved reading.
 *
 * **Account views** (All saved, a Reading status) read the library store,
 * whose server response already went through `visible_to()`: an unavailable
 * save arrives as its id and nothing else (ADR-044 §4).
 *
 * **Browser views** (own folders, history) still hold bare ids. Those resolve
 * through the *list* endpoint (`?id=1,2,3`), which applies the visibility
 * predicate, never through detail one id at a time: a stale localStorage id
 * must not become a way to learn about a record the viewer may not read.
 *
 * Either way, ids the predicate drops are reported as no longer available
 * rather than silently hidden.
 */
export function SavedView({
  view, collections, history, library, libraryLoad, libraryInterrupted = false, onRetryLibrary, onRemove, onRename, onDelete, onClearHistory, filters, folderControl,
}: SavedViewProps) {
  const accountView = view.kind === "saved" || view.kind === "status";
  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [interrupted, setInterrupted] = useState(false);
  const [layout, setLayout] = useState<LibraryLayout>("grid");
  const [sort, setSort] = useState<SortKey>("added");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [citing, setCiting] = useState<RecordListItem | null>(null);
  const [renaming, setRenaming] = useState(false);

  const folder = view.kind === "folder" ? collections.find((c) => c.id === view.id) : undefined;
  const statusFilter = view.kind === "status" ? view.status : null;
  const title = view.kind === "saved"
    ? "All saved"
    : view.kind === "status"
      ? readingStatusLabel(view.status)
      : view.kind === "history" ? "History" : folder?.name ?? "Folder";

  /* The account's saves this view shows, newest first. */
  const accountItems = useMemo(
    () => (accountView
      ? sortedItems(library).filter((i) => statusFilter === null || i.readingStatus === statusFilter)
      : []),
    [accountView, library, statusFilter],
  );

  /* The ids this view asks for, newest first. */
  const viewIds = useMemo<number[]>(() => {
    if (accountView) return accountItems.map((i) => i.recordId);
    if (view.kind === "history") return history.map((v) => v.recordId);
    return folder ? [...folder.recordIds].reverse() : [];
  }, [accountView, accountItems, view.kind, history, folder]);
  const idKey = accountView ? "" : viewIds.join(",");

  const load = useCallback(async () => {
    if (accountView) return;
    const ids = idKey ? idKey.split(",").map(Number) : [];
    if (ids.length === 0) {
      setRecords([]);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    setInterrupted(false);
    try {
      const pages = await Promise.all(
        chunk(ids, ID_CHUNK).map((part) => recordsApi.list({ id: part.join(","), page_size: ID_CHUNK })),
      );
      setRecords(pages.flatMap((p) => p.data.results ?? []));
    } catch (error) {
      setFailed(true);
      setInterrupted(isRequestTimeout(error));
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [idKey, accountView]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setSelected(new Set());
    setQuery("");
    setRenaming(false);
  }, [view.kind, folder?.id, statusFilter]);

  const shownRecords = useMemo(
    () => (accountView
      ? accountItems.flatMap((i) => (i.available && i.record ? [i.record] : []))
      : records),
    [accountView, accountItems, records],
  );
  const unavailableIds = accountView
    ? accountItems.filter((i) => !i.available).map((i) => i.recordId)
    : [];
  const isLoading = accountView ? libraryLoad === "idle" || libraryLoad === "loading" : loading;
  const isFailed = accountView ? libraryLoad === "error" : failed;
  const retry = accountView ? onRetryLibrary : () => void load();

  const visible = useMemo(() => {
    const order = new Map(viewIds.map((id, i) => [id, i]));
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? shownRecords.filter((r) =>
          r.title.toLowerCase().includes(needle) ||
          (r.authors ?? []).some((a) => (typeof a === "string" ? a : a?.name ?? "").toLowerCase().includes(needle)))
      : shownRecords;
    const sorted = [...matched];
    if (sort === "title") sorted.sort((a, b) => a.title.localeCompare(b.title));
    else if (sort === "year") sorted.sort((a, b) => (b.publication_year ?? 0) - (a.publication_year ?? 0));
    else sorted.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
    return sorted;
  }, [shownRecords, viewIds, query, sort]);

  const readingStatusOf = useMemo(
    () => Object.fromEntries(Object.values(library).map((i) => [i.recordId, i.readingStatus])),
    [library],
  );
  const viewedAt = useMemo(() => Object.fromEntries(history.map((v) => [v.recordId, v.viewedAt])), [history]);
  const unavailable = viewIds.length - shownRecords.length;

  const remove = (ids: number[]) => {
    onRemove(ids);
    setSelected(new Set());
  };

  const empty = view.kind === "history"
    ? { title: "No reading history yet", message: "Papers you open in this browser are listed here, newest first. It is cleared when you sign out." }
    : view.kind === "saved"
      ? { title: "No saved papers yet", message: "Save a paper from Discover or a paper's page and it follows your account." }
      : { title: `Nothing in ${title} yet`, message: "Save a paper from Discover or a paper's page to file it here." };
  const removeLabel = view.kind === "folder" ? "Remove from folder" : "Remove from library";

  const textButton = cn("min-h-10 rounded-lg px-3 text-small font-semibold text-stone-700 hover:bg-stone-100", COLOUR_TRANSITION, FOCUS_RING);

  return (
    <div>
      <div className="mb-section rounded-2xl border border-stone-200 bg-white p-card-compact md:p-card">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[12rem] flex-1">
          <span className="sr-only">Search this folder</span>
          <SearchGlyph className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-500" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by title or author"
            className="w-full rounded-lg border border-stone-300 bg-white py-2 pl-10 pr-3 text-body placeholder:text-stone-500 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
          />
        </label>
        {folderControl}
        <Select
          label="Sort"
          size="sm"
          inline
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
        >
          {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => <option key={key} value={key}>{SORT_LABELS[key]}</option>)}
        </Select>
        <div className="flex items-center rounded-lg border border-stone-300 bg-white p-0.5">
          {(["list", "grid"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setLayout(mode)}
              aria-label={`${mode === "list" ? "List" : "Grid"} view`}
              aria-pressed={layout === mode}
              className={cn("rounded-md px-2.5 py-1.5", COLOUR_TRANSITION, FOCUS_RING,
                layout === mode ? "bg-brand-50 text-brand" : "text-stone-500 hover:text-stone-800")}
            >
              <i className={cn("fas", mode === "list" ? "fa-list" : "fa-table-cells-large", "text-small")} aria-hidden />
            </button>
          ))}
        </div>
      </div>
      {filters && <div className="mt-3 border-t border-stone-200 pt-3">{filters}</div>}
      </div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        {renaming && folder ? (
          <input
            autoFocus
            defaultValue={folder.name}
            aria-label={`Rename ${folder.name}`}
            onBlur={(e) => { if (e.target.value.trim()) onRename(folder.id, e.target.value.trim()); setRenaming(false); }}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") setRenaming(false);
            }}
            className="rounded-lg border border-brand-200 px-3 py-1.5 font-display text-title font-semibold focus:border-brand focus:outline-none"
          />
        ) : (
          <h2 className="font-display text-title font-semibold text-stone-900">{title}</h2>
        )}
        <div className="flex items-center gap-1">
          {folder && !renaming && (
            <>
              <button type="button" onClick={() => setRenaming(true)} className={textButton}>Rename</button>
              <button type="button" onClick={() => onDelete(folder.id)} className={textButton}>Delete folder</button>
            </>
          )}
          {view.kind === "history" && history.length > 0 && (
            <button type="button" onClick={onClearHistory} className={textButton}>Clear history</button>
          )}
        </div>
      </div>


      {selected.size > 0 && view.kind !== "history" && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2">
          <span className="text-small font-semibold text-brand">Selected papers</span>
          <button type="button" onClick={() => remove([...selected])} className={cn(PILL_SECONDARY, "ml-auto min-h-9 px-3")}>
            {removeLabel}
          </button>
          <button type="button" onClick={() => setSelected(new Set())} className={textButton}>Clear</button>
        </div>
      )}

      {unavailable > 0 && !isLoading && !isFailed && (
        <p className="mb-3 flex flex-wrap items-center gap-x-2 rounded-xl border border-stone-200 bg-white px-3 py-2 text-small text-stone-700">
          <span>
            <i className="fas fa-eye-slash mr-1.5 text-stone-500" aria-hidden />
            {unavailable === 1 ? "1 saved paper is" : `${unavailable} saved papers are`} no longer available to you. They may have been unpublished or withdrawn.
          </span>
          {unavailableIds.length > 0 && (
            <button type="button" onClick={() => onRemove(unavailableIds)} className={cn(textButton, "min-h-8 px-2")}>
              Remove {unavailableIds.length === 1 ? "it" : "them"}
            </button>
          )}
        </p>
      )}

      {isLoading ? (
        <LoadingRegion label="Loading saved papers…" onRetry={retry} className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-xl border border-stone-200 bg-white motion-safe:animate-pulse" />)}
        </LoadingRegion>
      ) : isFailed ? (
        <ReadFailedState
          interrupted={accountView ? libraryInterrupted : interrupted}
          what="saved papers"
          title="Could not load these papers"
          message={accountView
            ? "Your saved papers are safe in your account; only loading them failed."
            : "This list is still stored in this browser; only fetching the papers failed."}
          onRetry={retry}
        />
      ) : visible.length === 0 ? (
        <EmptyState
          framed
          icon={query ? "fa-magnifying-glass" : "fa-folder-open"}
          title={query ? "No matches in this folder" : empty.title}
          message={query ? "Search looks at titles and author names." : empty.message}
        />
      ) : (
        <LibraryRecordTable
          records={visible}
          layout={layout}
          query={query}
          selected={selected}
          onToggleSelect={(id) => setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
          })}
          onToggleAll={() => setSelected((prev) => prev.size === visible.length ? new Set() : new Set(visible.map((r) => r.id)))}
          onCite={setCiting}
          onRemove={view.kind === "history" ? undefined : (id) => remove([id])}
          removeLabel={removeLabel}
          viewedAt={view.kind === "history" ? viewedAt : undefined}
          readingStatusOf={readingStatusOf}
        />
      )}

      <PaperCiteModal record={citing} isOpen={citing !== null} onClose={() => setCiting(null)} />
    </div>
  );
}
