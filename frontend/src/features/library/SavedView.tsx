import { useEffect, useMemo, useState } from "react";

import type { ReadingStatus } from "@/api/library";
import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { ButtonLink } from "@/components/ui/Button";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { Select } from "@/components/ui/Select";
import type { RowMenuItem } from "@/features/accounts/RowMenu";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import { useHistoryStore } from "@/store/history.store";
import { MAX_FOLDER_NAME, readingStatusLabel, sortedItems, type LibraryFolder, type LibraryItem } from "@/store/library.store";
import { cn } from "@/lib/utils";
import type { RecordListItem } from "@/types/records";

import { LibrarySearch } from "./LibrarySearch";
import type { ReadingView } from "./libraryViews";
import { SavedPaperList } from "./SavedPaperList";
import { ViewHeader } from "./ViewHeader";

type SortKey = "added" | "title" | "year";

const SORT_LABELS: Record<SortKey, string> = {
  added: "Date added",
  title: "Title A–Z",
  year:  "Year published",
};

/** What a saved paper and a history entry share: an unavailable one has no record. */
interface AccountEntry {
  recordId:  number;
  available: boolean;
  record?:   RecordListItem;
}

interface SavedViewProps {
  view:        ReadingView;
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
  onSetStatus: (record: RecordListItem, status: ReadingStatus | null) => void;
}

/**
 * One reading view: All saved, a Reading status, one of the reader's folders,
 * or History.
 *
 * Every view reads the account. The saves come from the library store, History
 * from the history store (IR-756). Both server responses already went through
 * `visible_to()`: an unavailable entry arrives as its id and nothing else
 * (ADR-044 §4), and is reported as no longer available rather than silently
 * hidden. A folder holds saves, so its papers are the saves it lists, in the
 * order they were filed (IR-572).
 *
 * IR-1311: the rail picks the view, so the toolbar is search and sort only.
 * What the view itself offers (rename or delete a folder, pause or clear
 * history, choosing papers to remove together) is in its ⋯ menu.
 */
export function SavedView({
  view, folders, library, libraryLoad, libraryInterrupted = false, onRetryLibrary, onRemove, onRename, onDelete, onSetStatus,
}: SavedViewProps) {
  const historyView = view.kind === "history";
  const historyStore = useHistoryStore();
  const [sort, setSort] = useState<SortKey>("added");
  const [query, setQuery] = useState("");
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [citing, setCiting] = useState<RecordListItem | null>(null);
  const [renaming, setRenaming] = useState(false);

  const folder = view.kind === "folder" ? folders.find((f) => f.id === view.id) : undefined;
  const statusFilter = view.kind === "status" ? view.status : null;
  const title = view.kind === "saved"
    ? "All saved"
    : view.kind === "status"
      ? readingStatusLabel(view.status)
      : historyView ? "History" : folder?.name ?? "Folder";

  /* History's most recent first, a folder's in filing order, and every other view's newest saved first. */
  const accountItems = useMemo<AccountEntry[]>(() => {
    if (historyView) return historyStore.items;
    if (view.kind === "folder") {
      return (folder?.recordIds ?? []).flatMap((id) => (library[id] ? [library[id]] : []));
    }
    return sortedItems(library).filter((i) => statusFilter === null || i.readingStatus === statusFilter);
  }, [historyView, historyStore.items, view.kind, folder, library, statusFilter]);

  const viewIds = useMemo(() => accountItems.map((i) => i.recordId), [accountItems]);

  useEffect(() => {
    setSelected(new Set());
    setSelecting(false);
    setQuery("");
    setRenaming(false);
  }, [view.kind, folder?.id, statusFilter]);

  const shownRecords = useMemo(
    () => accountItems.flatMap((i) => (i.available && i.record ? [i.record] : [])),
    [accountItems],
  );
  // History has no per-paper removal, only Clear history, so it offers none here.
  const unavailableIds = historyView ? [] : accountItems.filter((i) => !i.available).map((i) => i.recordId);
  const load = historyView ? historyStore.load : libraryLoad;
  const isLoading = load === "idle" || load === "loading";
  const isFailed = load === "error";
  const interrupted = historyView ? historyStore.interrupted : libraryInterrupted;
  const retry = historyView ? () => void historyStore.refresh() : onRetryLibrary;

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

  const stopSelecting = () => {
    setSelecting(false);
    setSelected(new Set());
  };
  const remove = (ids: number[]) => {
    onRemove(ids);
    stopSelecting();
  };

  const paused = historyStore.keepHistory === false;
  const empty = historyView
    ? paused
      ? { title: "History is paused", message: "Papers you open are not added while history is paused." }
      : { title: "No reading history yet", message: "Papers you open are listed here, newest first, on every device you sign in on." }
    : view.kind === "saved"
      ? { title: "No saved papers yet", message: "Save a paper from Discover or a paper's page and it follows your account." }
      : view.kind === "folder"
        ? { title: `Nothing in ${title} yet`, message: "File a paper here from its Save menu on Discover or its page." }
        : { title: `Nothing in ${title} yet`, message: "Choose a Reading status from a saved paper's ⋯ menu to file it here." };
  const removeLabel = view.kind === "folder" ? "Remove from folder" : "Remove from library";

  const note = historyView
    ? paused
      ? "History is paused: papers you open are not added. What is listed stays until you clear it."
      : "Your reading history is stored on your account, so it follows you to any device. Only you can see it."
    : view.kind === "folder"
      ? "Taking a paper out of a folder keeps it saved."
      : "Saves, reading status and folders follow your account.";

  const menu: RowMenuItem[] = [];
  if (!historyView && shownRecords.length > 0) {
    menu.push(selecting
      ? { key: "select", label: "Stop selecting", icon: "fa-xmark", onSelect: stopSelecting }
      : { key: "select", label: "Select papers", icon: "fa-square-check", onSelect: () => setSelecting(true) });
  }
  if (folder) {
    menu.push({ key: "rename", label: "Rename folder", icon: "fa-pen", onSelect: () => setRenaming(true) });
    menu.push({ key: "delete", label: "Delete folder", danger: true, onSelect: () => onDelete(folder.id) });
  }
  if (historyView) {
    if (historyStore.keepHistory !== null) {
      menu.push(paused
        ? { key: "keep", label: "Resume history", icon: "fa-play", onSelect: () => void historyStore.setKeepHistory(true) }
        : { key: "keep", label: "Pause history", icon: "fa-pause", onSelect: () => void historyStore.setKeepHistory(false) });
    }
    if (historyStore.items.length > 0) {
      menu.push({ key: "clear", label: "Clear history", danger: true, onSelect: () => void historyStore.clear() });
    }
  }

  const heading = renaming && folder ? (
    <input
      autoFocus
      defaultValue={folder.name}
      maxLength={MAX_FOLDER_NAME}
      aria-label={`Rename ${folder.name}`}
      onBlur={(e) => {
        const name = e.target.value.trim();
        if (name && name !== folder.name) onRename(folder.id, name);
        setRenaming(false);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") setRenaming(false);
      }}
      className="w-full max-w-md rounded-control border border-field px-3 py-1 font-display text-section font-semibold focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
    />
  ) : title;

  const quiet = cn("min-h-9 rounded-control px-3 text-small font-semibold text-stone-700 hover:bg-stone-100", COLOUR_TRANSITION, FOCUS_RING);

  return (
    <div>
      <ViewHeader title={heading} name={title} note={note} menu={menu} />

      <div className="mb-section flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1"><LibrarySearch label={`Search ${title}`} value={query} onChange={setQuery} /></div>
        <Select label="Sort" size="sm" inline value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
          {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => <option key={key} value={key}>{SORT_LABELS[key]}</option>)}
        </Select>
      </div>

      {historyView && historyStore.failure && (
        <p role="alert" className="mb-3 flex flex-wrap items-center gap-x-2 rounded-card border border-stone-300 bg-surface px-3 py-2 text-small text-brand">
          {historyStore.failure}
          <button type="button" onClick={historyStore.dismissFailure} className={cn("ml-auto rounded-control px-2 py-1 font-semibold hover:bg-stone-100", FOCUS_RING)}>
            Dismiss
          </button>
        </p>
      )}

      {selecting && (
        <div role="region" aria-label="Selected papers" className="mb-3 flex flex-wrap items-center gap-2 rounded-card border border-stone-300 bg-surface px-3 py-2">
          <span className="text-small font-semibold text-stone-800">
            {selected.size === 0 ? "Choose the papers to remove" : selected.size === 1 ? "1 paper chosen" : `${selected.size} papers chosen`}
          </span>
          <button
            type="button"
            onClick={() => setSelected((prev) => prev.size === visible.length ? new Set() : new Set(visible.map((r) => r.id)))}
            className={quiet}
          >
            {selected.size === visible.length && visible.length > 0 ? "Choose none" : "Choose all"}
          </button>
          <span className="ml-auto flex items-center gap-1">
            <button type="button" onClick={stopSelecting} className={quiet}>Cancel</button>
            <button
              type="button"
              disabled={selected.size === 0}
              onClick={() => remove([...selected])}
              className={cn(PILL_SECONDARY, "min-h-9 px-4 disabled:cursor-not-allowed disabled:opacity-50", FOCUS_RING)}
            >
              {removeLabel}
            </button>
          </span>
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
            <button type="button" onClick={() => onRemove(unavailableIds)} className={cn(quiet, "min-h-8 px-2")}>
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
          interrupted={interrupted}
          what={historyView ? "reading history" : "saved papers"}
          title="Could not load these papers"
          message={historyView
            ? "Your history is safe in your account; only loading it failed."
            : "Your saved papers and folders are safe in your account; only loading them failed."}
          onRetry={retry}
        />
      ) : visible.length === 0 ? (
        <EmptyState
          framed
          icon={query ? "fa-magnifying-glass" : "fa-folder-open"}
          title={query ? `Nothing matches “${query.trim()}”` : empty.title}
          message={query ? "Search looks at titles and author names." : empty.message}
          // The next useful step (audit LAY-06): papers are saved from Discover.
          action={query || historyView ? undefined : <ButtonLink to="/" variant="outline">Browse Discover</ButtonLink>}
        />
      ) : (
        <SavedPaperList
          records={visible}
          query={query}
          selecting={selecting}
          selected={selected}
          onToggleSelect={(id) => setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
          })}
          onCite={setCiting}
          onRemove={historyView ? undefined : (id) => remove([id])}
          removeLabel={removeLabel}
          viewedAt={historyView ? viewedAt : undefined}
          readingStatusOf={readingStatusOf}
          onSetStatus={onSetStatus}
        />
      )}

      <PaperCiteModal record={citing} isOpen={citing !== null} onClose={() => setCiting(null)} />
    </div>
  );
}
