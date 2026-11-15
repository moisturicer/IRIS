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
import type { Collection } from "@/lib/recordLibrary";
import { useHistoryStore } from "@/store/history.store";
import { readingStatusLabel, sortedItems, type LibraryItem } from "@/store/library.store";
import { cn } from "@/lib/utils";
import type { RecordListItem } from "@/types/records";

import { LibraryRecordTable, type LibraryLayout } from "./LibraryRecordTable";
import type { LibraryView } from "./ReadingPanel";
import { SearchGlyph } from "@/components/brand/IrisBrand";
import { SELECTED_SEGMENT } from "@/components/ui/highlightRoles";

type SortKey = "added" | "title" | "year";

/** What a saved paper and a history entry share: an unavailable one has no record. */
interface AccountEntry {
  recordId:  number;
  available: boolean;
  record?:   RecordListItem;
}

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
  /** The account's saves (IR-566), keyed by Record id. */
  library:     Record<number, LibraryItem>;
  libraryLoad: "idle" | "loading" | "ready" | "error";
  /** `libraryLoad` is `error` because the read timed out (IR-906). */
  libraryInterrupted?: boolean;
  onRetryLibrary: () => void;
  onRemove:    (ids: number[]) => void;
  onRename:    (id: string, name: string) => void;
  onDelete:    (id: string) => void;
  /** The Reading status filters, set under the search in the toolbar. */
  filters?:       ReactNode;
  /** The Folder picker, set beside Sort in the toolbar. */
  folderControl?: ReactNode;
}

/**
 * One view of the reader's saved reading.
 *
 * **Account views** (All saved, a Reading status, History) read the library
 * and history stores, whose server responses already went through
 * `visible_to()`: an unavailable entry arrives as its id and nothing else
 * (ADR-044 §4, and its IR-756 amendment for History).
 *
 * **Browser views** (own folders) still hold bare ids. Those resolve
 * through the *list* endpoint (`?id=1,2,3`), which applies the visibility
 * predicate, never through detail one id at a time: a stale localStorage id
 * must not become a way to learn about a record the viewer may not read.
 *
 * Either way, ids the predicate drops are reported as no longer available
 * rather than silently hidden.
 */
export function SavedView({
  view, collections, library, libraryLoad, libraryInterrupted = false, onRetryLibrary, onRemove, onRename, onDelete, filters, folderControl,
}: SavedViewProps) {
  const savesView = view.kind === "saved" || view.kind === "status";
  const historyView = view.kind === "history";
  const accountView = savesView || historyView;
  const historyStore = useHistoryStore();
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

  /* The account's saves or history this view shows, newest first. */
  const accountItems = useMemo<AccountEntry[]>(
    () => (savesView
      ? sortedItems(library).filter((i) => statusFilter === null || i.readingStatus === statusFilter)
      : historyView ? historyStore.items : []),
    [savesView, historyView, library, historyStore.items, statusFilter],
  );

  /* The ids this view asks for, newest first. */
  const viewIds = useMemo<number[]>(() => {
    if (accountView) return accountItems.map((i) => i.recordId);
    return folder ? [...folder.recordIds].reverse() : [];
  }, [accountView, accountItems, folder]);
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
  // History has no per-paper removal, only Clear history, so it offers none here.
  const unavailableIds = savesView
    ? accountItems.filter((i) => !i.available).map((i) => i.recordId)
    : [];
  const accountLoad = historyView ? historyStore.load : libraryLoad;
  const accountInterrupted = historyView ? historyStore.interrupted : libraryInterrupted;
  const isLoading = accountView ? accountLoad === "idle" || accountLoad === "loading" : loading;
  const isFailed = accountView ? accountLoad === "error" : failed;
  const retry = historyView ? () => void historyStore.refresh() : accountView ? onRetryLibrary : () => void load();

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
  const viewedAt = useMemo(
    () => Object.fromEntries(historyStore.items.flatMap((v) => (v.viewedAt ? [[v.recordId, v.viewedAt]] : []))),
    [historyStore.items],
  );
  const unavailable = viewIds.length - shownRecords.length;

  const remove = (ids: number[]) => {
    onRemove(ids);
    setSelected(new Set());
  };

  const empty = historyView
    ? historyStore.keepHistory === false
      ? { title: "History is paused", message: "Papers you open are not added while history is paused." }
      : { title: "No reading history yet", message: "Papers you open are listed here, newest first, on every device you sign in on." }
    : view.kind === "saved"
      ? { title: "No saved papers yet", message: "Save a paper from Discover or a paper's page and it follows your account." }
      : { title: `Nothing in ${title} yet`, message: "Save a paper from Discover or a paper's page to file it here." };
  const removeLabel = view.kind === "folder" ? "Remove from folder" : "Remove from library";

  const textButton = cn("min-h-10 rounded-control px-3 text-small font-semibold text-stone-700 hover:bg-stone-100", COLOUR_TRANSITION, FOCUS_RING);

  return (
    <div>
      <div className="mb-section rounded-card border border-stone-200 bg-white p-card-compact md:p-card">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-[12rem] flex-1">
          <span className="sr-only">Search this folder</span>
          <SearchGlyph className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-stone-500" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by title or author"
            className="w-full rounded-control border border-field bg-white py-2 pl-10 pr-3 text-body placeholder:text-stone-600 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
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
        <div className="flex items-center rounded-control border border-stone-300 bg-white p-0.5">
          {(["list", "grid"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setLayout(mode)}
              aria-label={`${mode === "list" ? "List" : "Grid"} view`}
              aria-pressed={layout === mode}
              className={cn("rounded-control px-2.5 py-1.5", COLOUR_TRANSITION, FOCUS_RING,
                layout === mode ? SELECTED_SEGMENT : "text-stone-500 hover:text-stone-800")}
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
            className="rounded-control border border-field px-3 py-1.5 font-display text-title font-semibold focus:border-brand focus:outline-none"
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
          {historyView && historyStore.items.length > 0 && (
            <button type="button" onClick={() => void historyStore.clear()} className={textButton}>Clear history</button>
          )}
        </div>
      </div>

      {historyView && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-card border border-stone-200 bg-white px-3 py-2">
          <p className="text-small text-stone-700">
            {historyStore.keepHistory === false
              ? "History is paused: papers you open are not added. What is listed stays until you clear it."
              : "Your reading history is stored on your account, so it follows you to any device. Only you can see it."}
          </p>
          <label className="flex min-h-10 items-center gap-2 text-small font-semibold text-stone-800">
            <input
              type="checkbox"
              checked={historyStore.keepHistory !== false}
              disabled={historyStore.keepHistory === null}
              onChange={(e) => void historyStore.setKeepHistory(e.target.checked)}
              className={cn("accent-brand", FOCUS_RING)}
            />
            Keep reading history
          </label>
        </div>
      )}

      {historyView && historyStore.failure && (
        <p role="alert" className="mb-3 flex flex-wrap items-center gap-x-2 rounded-card border border-stone-300 bg-surface px-3 py-2 text-small text-brand">
          {historyStore.failure}
          <button type="button" onClick={historyStore.dismissFailure} className={cn("ml-auto rounded-control px-2 py-1 font-semibold hover:bg-stone-100", FOCUS_RING)}>
            Dismiss
          </button>
        </p>
      )}


      {selected.size > 0 && !historyView && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-card border border-stone-300 bg-surface px-3 py-2">
          <span className="text-small font-semibold text-brand">Selected papers</span>
          <button type="button" onClick={() => remove([...selected])} className={cn(PILL_SECONDARY, "ml-auto min-h-9 px-3")}>
            {removeLabel}
          </button>
          <button type="button" onClick={() => setSelected(new Set())} className={textButton}>Clear</button>
        </div>
      )}

      {unavailable > 0 && !isLoading && !isFailed && (
        <p className="mb-3 flex flex-wrap items-center gap-x-2 rounded-card border border-stone-200 bg-white px-3 py-2 text-small text-stone-700">
          <span>
            <i className="fas fa-eye-slash mr-1.5 text-stone-500" aria-hidden />
            {historyView
              ? unavailable === 1 ? "1 paper in your history is" : `${unavailable} papers in your history are`
              : unavailable === 1 ? "1 saved paper is" : `${unavailable} saved papers are`} no longer available to you. They may have been unpublished or withdrawn.
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
          {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-card border border-stone-200 bg-white motion-safe:animate-pulse" />)}
        </LoadingRegion>
      ) : isFailed ? (
        <ReadFailedState
          interrupted={accountView ? accountInterrupted : interrupted}
          what={historyView ? "reading history" : "saved papers"}
          title="Could not load these papers"
          message={historyView
            ? "Your history is safe in your account; only loading it failed."
            : accountView
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
          onRemove={historyView ? undefined : (id) => remove([id])}
          removeLabel={removeLabel}
          viewedAt={historyView ? viewedAt : undefined}
          readingStatusOf={readingStatusOf}
        />
      )}

      <PaperCiteModal record={citing} isOpen={citing !== null} onClose={() => setCiting(null)} />
    </div>
  );
}
