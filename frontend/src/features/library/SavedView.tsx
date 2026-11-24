import { useEffect, useMemo, useState, type ReactNode } from "react";

import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { ButtonLink } from "@/components/ui/Button";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { Select } from "@/components/ui/Select";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import { readingStatusLabel, sortedItems, type LibraryFolder, type LibraryItem } from "@/store/library.store";
import { cn } from "@/lib/utils";
import type { RecordListItem } from "@/types/records";

import { LibraryRecordTable, type LibraryLayout } from "./LibraryRecordTable";
import { LibrarySearch } from "./LibraryToolbar";
import { FolderShelf, type LibraryView } from "./ReadingPanel";
import { SELECTED_SEGMENT } from "@/components/ui/highlightRoles";

type SortKey = "added" | "title" | "year";

const SORT_LABELS: Record<SortKey, string> = {
  added: "Date added",
  title: "Title A–Z",
  year:  "Year published",
};

/** A saved paper: an unavailable one has no record. */
interface AccountEntry {
  recordId:  number;
  available: boolean;
  record?:   RecordListItem;
}

interface SavedViewProps {
  view:        Exclude<LibraryView, { kind: "research" }>;
  /** The reader's own folders (IR-572); every Record in one is also a save. */
  folders:     LibraryFolder[];
  /** The account's saves (IR-566), keyed by Record id. */
  library:     Record<number, LibraryItem>;
  libraryLoad: "idle" | "loading" | "ready" | "error";
  /** `libraryLoad` is `error` because the read timed out (IR-906). */
  libraryInterrupted?: boolean;
  onRetryLibrary: () => void;
  onRemove:    (ids: number[]) => void;
  onRename:    (id: number, name: string) => void;
  onDelete:    (id: number) => void;
  /** The Reading status filters, set under the Papers heading. */
  filters?:       ReactNode;
  /** How many folders the account may hold, when the server has said. */
  folderLimit?:   number | null;
  /** Open a folder, or All saved again. */
  onOpenView?:    (view: Exclude<LibraryView, { kind: "research" }>) => void;
  onCreateFolder?: (name: string) => void;
  /** Opens the History pop-up (IR-1331), shown on the folders for a reader with no Overview. */
  onManageHistory?: () => void;
}

/**
 * One view of the reader's saved reading.
 *
 * Every view reads the account's library store: All saved, a Reading status
 * and one of the reader's own folders. History is a pop-up of its own
 * (`HistoryDialog`, IR-1331). The server's answer already went through `visible_to()`: an
 * unavailable entry arrives as its id and nothing else (ADR-044 §4), and is
 * reported as no longer available rather than silently hidden. A folder holds
 * saves, so its papers are the saves it lists, in the order they were filed
 * (IR-572).
 */
export function SavedView({
  view, folders, library, libraryLoad, libraryInterrupted = false, onRetryLibrary, onRemove, onRename, onDelete, filters,
  folderLimit = null, onOpenView, onCreateFolder, onManageHistory,
}: SavedViewProps) {
  const [layout, setLayout] = useState<LibraryLayout>("grid");
  const [sort, setSort] = useState<SortKey>("added");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [citing, setCiting] = useState<RecordListItem | null>(null);

  const folder = view.kind === "folder" ? folders.find((f) => f.id === view.id) : undefined;
  /* All saved and a Reading status show the folders above the papers (IR-1324). */
  const topLevel = view.kind === "saved" || view.kind === "status";
  const statusFilter = view.kind === "status" ? view.status : null;
  const title = view.kind === "saved"
    ? "All saved"
    : view.kind === "status"
      ? readingStatusLabel(view.status)
      : folder?.name ?? "Folder";

  /* The entries this view shows: a folder's in filing order, newest first,
     and every other view's newest saved first. */
  const accountItems = useMemo<AccountEntry[]>(() => {
    if (view.kind === "folder") {
      return (folder?.recordIds ?? []).flatMap((id) => (library[id] ? [library[id]] : []));
    }
    return sortedItems(library).filter((i) => statusFilter === null || i.readingStatus === statusFilter);
  }, [view.kind, folder, library, statusFilter]);

  /* The ids this view shows, in its order. */
  const viewIds = useMemo(() => accountItems.map((i) => i.recordId), [accountItems]);

  useEffect(() => {
    setSelected(new Set());
    setQuery("");
  }, [view.kind, folder?.id, statusFilter]);

  const shownRecords = useMemo(
    () => accountItems.flatMap((i) => (i.available && i.record ? [i.record] : [])),
    [accountItems],
  );
  const unavailableIds = accountItems.filter((i) => !i.available).map((i) => i.recordId);
  const isLoading = libraryLoad === "idle" || libraryLoad === "loading";
  const isFailed = libraryLoad === "error";

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
  const unavailable = viewIds.length - shownRecords.length;

  const remove = (ids: number[]) => {
    onRemove(ids);
    setSelected(new Set());
  };

  const empty = view.kind === "saved"
      ? { title: "No saved papers yet", message: "Save a paper from Discover or a paper's page and it follows your account." }
      : view.kind === "folder"
        ? { title: `Nothing in ${title} yet`, message: "File a paper here from its Save menu on Discover or its page." }
        : { title: `Nothing in ${title} yet`, message: "Save a paper from Discover or a paper's page to file it here." };
  const removeLabel = view.kind === "folder" ? "Remove from folder" : "Remove from library";

  const textButton = cn("min-h-10 rounded-control px-3 text-small font-semibold text-stone-700 hover:bg-stone-100", COLOUR_TRANSITION, FOCUS_RING);

  return (
    <div>
      <div className="mb-section flex flex-wrap items-center gap-2">
        <LibrarySearch
          label={folder ? "Search this folder" : "Search saved papers"}
          value={query}
          onChange={setQuery}
          className="basis-full sm:basis-0"
        />
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

      {topLevel && onOpenView && onCreateFolder && (
        <FolderShelf
          folders={folders}
          limit={folderLimit}
          onManageHistory={onManageHistory}
          onOpen={(next) => { if (next.kind !== "research") onOpenView(next); }}
          onCreate={onCreateFolder}
          onRename={onRename}
          onDelete={onDelete}
        />
      )}

      {!topLevel && onOpenView && (
        <button
          type="button"
          onClick={() => onOpenView({ kind: "saved" })}
          className={cn(textButton, "-mx-3 mb-1 inline-flex items-center gap-2 text-brand")}
        >
          <i className="fas fa-arrow-left text-label" aria-hidden />
          All saved papers
        </button>
      )}
      <h2 className={cn("font-display text-title font-semibold text-stone-900", topLevel && filters ? "mb-2" : "mb-4")}>{topLevel ? "Papers" : title}</h2>

      {topLevel && filters && <div className="mb-4">{filters}</div>}

      {selected.size > 0 && (
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
        <LoadingRegion label="Loading saved papers…" onRetry={onRetryLibrary} className="space-y-2">
          {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-card border border-stone-200 bg-white motion-safe:animate-pulse" />)}
        </LoadingRegion>
      ) : isFailed ? (
        <ReadFailedState
          interrupted={libraryInterrupted}
          what="saved papers"
          title="Could not load these papers"
          message="Your saved papers and folders are safe in your account; only loading them failed."
          onRetry={onRetryLibrary}
        />
      ) : visible.length === 0 ? (
        <EmptyState
          framed
          icon={query ? "fa-magnifying-glass" : "fa-folder-open"}
          title={query ? (folder ? "No matches in this folder" : "No matches") : empty.title}
          message={query ? "Search looks at titles and author names." : empty.message}
          // The next useful step (audit LAY-06): papers are saved from Discover.
          action={query ? undefined : <ButtonLink to="/" variant="outline">Browse Discover</ButtonLink>}
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
          onRemove={(id) => remove([id])}
          removeLabel={removeLabel}
          readingStatusOf={readingStatusOf}
        />
      )}

      <PaperCiteModal record={citing} isOpen={citing !== null} onClose={() => setCiting(null)} />
    </div>
  );
}
