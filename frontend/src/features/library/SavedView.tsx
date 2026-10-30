import { useCallback, useEffect, useMemo, useState } from "react";

import { recordsApi } from "@/api/records";
import { EmptyState } from "@/components/shared/EmptyState";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { PaperCiteModal } from "@/features/discover/PaperCiteModal";
import { isStatusFolder, type Collection, type ReadingVisit } from "@/lib/recordLibrary";
import { cn } from "@/lib/utils";
import type { RecordListItem } from "@/types/records";

import { LibraryRecordTable, type LibraryLayout } from "./LibraryRecordTable";
import type { LibraryView } from "./ReadingPanel";

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
  starredIds:  number[];
  history:     ReadingVisit[];
  onRemove:    (ids: number[]) => void;
  onToggleStar: (id: number) => void;
  onRename:    (id: string, name: string) => void;
  onDelete:    (id: string) => void;
  onClearHistory: () => void;
}

/**
 * One folder of this browser's saved reading, liked papers, or history.
 *
 * Saved ids resolve through the *list* endpoint (`?id=1,2,3`), which applies
 * the visibility predicate, never through detail one id at a time: a stale
 * localStorage id must not become a way to learn about a record the viewer
 * may not read. Ids the predicate drops are reported as no longer available
 * rather than silently hidden.
 */
export function SavedView({
  view, collections, starredIds, history, onRemove, onToggleStar, onRename, onDelete, onClearHistory,
}: SavedViewProps) {
  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [layout, setLayout] = useState<LibraryLayout>("list");
  const [sort, setSort] = useState<SortKey>("added");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [citing, setCiting] = useState<RecordListItem | null>(null);
  const [renaming, setRenaming] = useState(false);

  const folder = view.kind === "folder" ? collections.find((c) => c.id === view.id) : undefined;
  const ownFolder = folder && !isStatusFolder(folder.id);
  const title = view.kind === "starred" ? "Liked papers" : view.kind === "history" ? "History" : folder?.name ?? "Folder";

  /* The ids this view asks for, newest first. */
  const viewIds = useMemo<number[]>(() => {
    if (view.kind === "starred") return [...starredIds].reverse();
    if (view.kind === "history") return history.map((v) => v.recordId);
    return folder ? [...folder.recordIds].reverse() : [];
  }, [view.kind, starredIds, history, folder]);
  const idKey = viewIds.join(",");

  const load = useCallback(async () => {
    const ids = idKey ? idKey.split(",").map(Number) : [];
    if (ids.length === 0) {
      setRecords([]);
      setLoading(false);
      setFailed(false);
      return;
    }
    setLoading(true);
    setFailed(false);
    try {
      const pages = await Promise.all(
        chunk(ids, ID_CHUNK).map((part) => recordsApi.list({ id: part.join(","), page_size: ID_CHUNK })),
      );
      setRecords(pages.flatMap((p) => p.data.results ?? []));
    } catch {
      setFailed(true);
      setRecords([]);
    } finally {
      setLoading(false);
    }
  }, [idKey]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setSelected(new Set());
    setQuery("");
    setRenaming(false);
  }, [view.kind, folder?.id]);

  const visible = useMemo(() => {
    const order = new Map(viewIds.map((id, i) => [id, i]));
    const needle = query.trim().toLowerCase();
    const matched = needle
      ? records.filter((r) =>
          r.title.toLowerCase().includes(needle) ||
          (r.authors ?? []).some((a) => (typeof a === "string" ? a : a?.name ?? "").toLowerCase().includes(needle)))
      : records;
    const sorted = [...matched];
    if (sort === "title") sorted.sort((a, b) => a.title.localeCompare(b.title));
    else if (sort === "year") sorted.sort((a, b) => (b.publication_year ?? 0) - (a.publication_year ?? 0));
    else sorted.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
    return sorted;
  }, [records, viewIds, query, sort]);

  const viewedAt = useMemo(() => Object.fromEntries(history.map((v) => [v.recordId, v.viewedAt])), [history]);
  const unavailable = viewIds.length - records.length;

  const remove = (ids: number[]) => {
    onRemove(ids);
    setSelected(new Set());
  };

  const empty = view.kind === "starred"
    ? { title: "No liked papers yet", message: "Tap the star on any paper to keep it here." }
    : view.kind === "history"
      ? { title: "No reading history yet", message: "Papers you open are listed here, newest first." }
      : { title: `Nothing in ${title} yet`, message: "Save a paper from Discover or a paper's page to file it here." };

  const textButton = cn("min-h-10 rounded-lg px-3 text-small font-semibold text-stone-700 hover:bg-stone-100", COLOUR_TRANSITION, FOCUS_RING);

  return (
    <div>
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
          {ownFolder && !renaming && (
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

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="relative min-w-[12rem] flex-1">
          <span className="sr-only">Search this folder</span>
          <i className="fas fa-magnifying-glass pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-small text-stone-500" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by title or author"
            className="w-full rounded-xl border border-stone-200 bg-white py-2.5 pl-10 pr-3 text-body placeholder:text-stone-500 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
          />
        </label>
        <label className="flex items-center gap-2 text-small text-stone-600">
          Sort
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="rounded-lg border border-stone-200 bg-white px-2 py-2 text-small text-stone-800 focus:border-brand focus:outline-none"
          >
            {(Object.keys(SORT_LABELS) as SortKey[]).map((key) => <option key={key} value={key}>{SORT_LABELS[key]}</option>)}
          </select>
        </label>
        <div className="flex items-center rounded-lg border border-stone-200 bg-white p-0.5">
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

      {selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-brand-200 bg-brand-50 px-3 py-2">
          <span className="text-small font-semibold text-brand">Selected papers</span>
          <button type="button" onClick={() => remove([...selected])} className={cn(PILL_SECONDARY, "ml-auto min-h-9 px-3")}>
            {view.kind === "starred" ? "Unlike" : "Remove from library"}
          </button>
          <button type="button" onClick={() => setSelected(new Set())} className={textButton}>Clear</button>
        </div>
      )}

      {unavailable > 0 && !loading && !failed && (
        <p className="mb-3 rounded-xl border border-stone-200 bg-white px-3 py-2 text-small text-stone-700">
          <i className="fas fa-eye-slash mr-1.5 text-stone-500" aria-hidden />
          Some saved papers are no longer available to you. They may have been unpublished or withdrawn.
        </p>
      )}

      {loading ? (
        <div className="space-y-2" role="status">
          <span className="sr-only">Loading saved papers…</span>
          {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-xl border border-stone-200 bg-white motion-safe:animate-pulse" aria-hidden />)}
        </div>
      ) : failed ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-plug-circle-xmark"
          title="Could not load these papers"
          message="Your saved list is still stored in this browser; only fetching the papers failed."
          action={<button type="button" onClick={() => void load()} className={cn(PILL_SECONDARY, FOCUS_RING)}>Try again</button>}
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
          starred={new Set(starredIds)}
          onToggleStar={onToggleStar}
          onCite={setCiting}
          onRemove={(id) => remove([id])}
          viewedAt={view.kind === "history" ? viewedAt : undefined}
        />
      )}

      <PaperCiteModal record={citing} isOpen={citing !== null} onClose={() => setCiting(null)} />
    </div>
  );
}
