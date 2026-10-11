import { useCallback, useEffect, useId, useMemo, useState } from "react";

import { opportunitiesApi } from "@/api/opportunities";
import { PageHeader } from "@/components/layout/PageHeader";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import {
  getSavedOpportunityIds,
  pruneSavedOpportunities,
  toggleSavedOpportunity,
} from "@/lib/opportunityLibrary";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import type { Opportunity, OpportunityType } from "@/types/opportunities";

import { OpportunityFormDialog } from "./OpportunityFormDialog";
import { OpportunityRow } from "./OpportunityRow";
import {
  DEADLINE_GROUPS,
  OPPORTUNITY_TYPES,
  byBoardOrder,
  deadlineGroup,
  matchesQuery,
} from "./opportunityUtils";

/** A filter chip, as My Reviews draws them: soft maroon when on. */
function chipClass(on: boolean) {
  return cn(
    "inline-flex shrink-0 items-center gap-1.5 min-h-11 lg:min-h-9 px-3 rounded-full border text-small font-medium whitespace-nowrap",
    COLOUR_TRANSITION,
    FOCUS_RING,
    on ? "border-brand bg-brand-50 text-brand" : "border-stone-200 bg-white text-stone-700 hover:border-stone-400",
    "disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:border-stone-200",
  );
}

/** Which sheet is open: none, a new call, or an existing one being edited. */
type FormTarget = null | "new" | Opportunity;

/**
 * Calls & Conferences: a deadline board (IR-121, redesigned in IR-530).
 *
 * The one question it answers is "what can I still apply to, and by when", so
 * the board is a single column grouped by how soon each call closes, in date
 * order inside each group; a featured call is starred, not moved. Closed calls
 * stay in a last group, so someone mid-application can still find the page,
 * until the server drops them a month after the deadline.
 *
 * RDCO, KTTO and Advisers post here, and change what they posted. The page
 * offers that only when the server says so (`can_post`, `can_edit`); the API
 * is the boundary either way.
 *
 * Saving is per-browser (`lib/opportunityLibrary`), and the page says so.
 * There is no server-side bookmark, and no in-app reminder: the calendar
 * action hands over an .ics file the viewer's own calendar keeps.
 */
export function CallsAndConferencesPage() {
  const addToast = useUIStore((s) => s.addToast);
  const ids = useId();

  const [items,    setItems]    = useState<Opportunity[]>([]);
  const [canPost,  setCanPost]  = useState(false);
  const [loading,  setLoading]  = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const [activeType, setActiveType] = useState<OpportunityType | null>(null);
  const [query,      setQuery]      = useState("");
  const [savedOnly,  setSavedOnly]  = useState(false);
  const [savedIds,   setSavedIds]   = useState<number[]>(() => getSavedOpportunityIds());

  const [icsBusy,   setIcsBusy]   = useState<number | null>(null);
  const [icsFailed, setIcsFailed] = useState<number | null>(null);

  const [formTarget, setFormTarget] = useState<FormTarget>(null);
  const [deleting,   setDeleting]   = useState<Opportunity | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
    opportunitiesApi
      .board()
      .then((board) => {
        if (cancelled) return;
        setItems([...board.items].sort(byBoardOrder));
        setCanPost(board.can_post);
        // The whole board is here, so a saved id that is not on it belongs to
        // a call that was deleted or has dropped off: forget it.
        setSavedIds(pruneSavedOpportunities(board.items.map((o) => o.id)));
      })
      .catch(() => { if (!cancelled) setLoadFailed(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => load(), [load]);

  // ---- Filtering ---------------------------------------------------------

  const savedSet = useMemo(() => new Set(savedIds), [savedIds]);
  /** Saved calls that are on the board now, which is what the Saved chip counts. */
  const savedOnBoard = useMemo(() => items.filter((o) => savedSet.has(o.id)).length, [items, savedSet]);

  /** Everything the search and saved filters keep, before the type filter. */
  const searched = useMemo(
    () => items.filter((o) => matchesQuery(o, query) && (!savedOnly || savedSet.has(o.id))),
    [items, query, savedOnly, savedSet],
  );

  const visible = useMemo(
    () => searched.filter((o) => activeType === null || o.opportunity_type === activeType),
    [searched, activeType],
  );

  const groups = useMemo(
    () =>
      DEADLINE_GROUPS
        .map((g) => ({ ...g, items: visible.filter((o) => deadlineGroup(o) === g.id) }))
        .filter((g) => g.items.length > 0),
    [visible],
  );

  /** Each type chip counts what it would show, given the search and saved filters. */
  const typeCounts = useMemo(() => {
    const counts = new Map<OpportunityType, number>();
    for (const o of searched) counts.set(o.opportunity_type, (counts.get(o.opportunity_type) ?? 0) + 1);
    return counts;
  }, [searched]);

  const openCount = useMemo(() => items.filter((o) => !o.is_closed).length, [items]);
  const filtered  = activeType !== null || query.trim() !== "" || savedOnly;

  const clearFilters = () => {
    setActiveType(null);
    setQuery("");
    setSavedOnly(false);
  };

  // ---- Actions -----------------------------------------------------------

  const handleToggleSave = (id: number) => {
    toggleSavedOpportunity(id);
    setSavedIds(getSavedOpportunityIds());
  };

  const handleDownloadIcs = async (o: Opportunity) => {
    setIcsBusy(o.id);
    setIcsFailed(null);
    try {
      const { data } = await opportunitiesApi.calendar(o.id);
      // Fetched with auth then handed to the browser as a blob: a plain link
      // to the endpoint would arrive unauthenticated and 401.
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${o.title.replace(/[^\w\s-]/g, "").slice(0, 60).trim() || "opportunity"}.ics`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // Said on the row it failed for, not by replacing the whole board.
      setIcsFailed(o.id);
    } finally {
      setIcsBusy(null);
    }
  };

  const handleSaved = (saved: Opportunity, created: boolean) => {
    setItems((current) =>
      [...current.filter((o) => o.id !== saved.id), saved].sort(byBoardOrder),
    );
    setFormTarget(null);
    addToast({ type: "success", message: created ? "Call posted." : "Changes saved." });
  };

  const confirmDelete = async () => {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await opportunitiesApi.remove(deleting.id);
      setItems((current) => current.filter((o) => o.id !== deleting.id));
      setDeleting(null);
      addToast({ type: "success", message: "Call deleted." });
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      setDeleteError(
        status === 403 || status === 404
          ? "You can no longer delete this call. It may already be gone."
          : "Could not delete the call. Check your connection and try again.",
      );
    } finally {
      setDeleteBusy(false);
    }
  };

  // ---- Render ------------------------------------------------------------

  const postButton = canPost && (
    <button type="button" onClick={() => setFormTarget("new")} className={cn(PILL_PRIMARY, FOCUS_RING)}>
      <i className="fas fa-plus" aria-hidden="true" />
      Post a call
    </button>
  );

  const ready = !loading && !loadFailed;

  const summary = !ready
    ? ""
    : filtered
      ? `Showing ${visible.length} of ${items.length} ${items.length === 1 ? "call" : "calls"}.`
      : `${openCount} open ${openCount === 1 ? "call" : "calls"}${items.length > openCount ? `, ${items.length - openCount} recently closed` : ""}.` +
        (savedOnBoard > 0 ? " Saved calls are kept in this browser only." : "");

  return (
    <div className="p-4 sm:p-6 max-w-screen-2xl mx-auto">
      <PageHeader
        title="Calls & Conferences"
        description="Internal research calls, conference deadlines and funding windows, posted by CIT-U offices and advisers. Soonest deadline first."
        actions={postButton || undefined}
      />

      {/* ---- Search and filters ------------------------------------------ */}
      {/* Search first, in its own row under the title: it is the first thing
          a reader reaches for, and at the end of the chip row it was missed.
          Counts appear only once there is a board to count; a 0 before the
          data arrives would be a number IRIS does not know. */}
      <div className="space-y-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="flex-1 min-w-0 max-w-md">
            <Input
              id={`${ids}-search`}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search calls"
              aria-label="Search calls by title, office or tag"
              disabled={loadFailed}
              leading={<i className="fas fa-magnifying-glass text-xs" aria-hidden="true" />}
            />
          </div>
          <button
            type="button"
            aria-pressed={savedOnly}
            aria-describedby={`${ids}-saved-hint`}
            onClick={() => setSavedOnly((v) => !v)}
            disabled={loadFailed}
            className={chipClass(savedOnly)}
          >
            <i className={cn(savedOnly ? "fas" : "far", "fa-bookmark text-3xs")} aria-hidden="true" />
            Saved
            {ready && <span className="tabular-nums opacity-80">{savedOnBoard}</span>}
          </button>
        </div>

        {/* One scrolling row on a phone, cued by the chip cut off at the edge,
            so five chips do not stack into four rows; wrapped from `sm` up. */}
        <div
          role="group"
          aria-label="Filter by type"
          className="flex gap-2 overflow-x-auto scrollbar-none -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap sm:overflow-visible"
        >
          <button
            type="button"
            aria-pressed={activeType === null}
            onClick={() => setActiveType(null)}
            disabled={loadFailed}
            className={chipClass(activeType === null)}
          >
            All
            {ready && <span className="tabular-nums opacity-80">{searched.length}</span>}
          </button>
          {OPPORTUNITY_TYPES.map((t) => (
            <button
              key={t.id}
              type="button"
              aria-pressed={activeType === t.id}
              onClick={() => setActiveType(activeType === t.id ? null : t.id)}
              disabled={loadFailed}
              className={chipClass(activeType === t.id)}
            >
              <i className={cn("fas", t.icon, "text-3xs")} aria-hidden="true" />
              {t.label}
              {ready && <span className="tabular-nums opacity-80">{typeCounts.get(t.id) ?? 0}</span>}
            </button>
          ))}
        </div>
      </div>

      {/* Always rendered, so a change to it is what a screen reader hears. */}
      <p role="status" aria-live="polite" className="text-small text-stone-600 min-h-5 mb-section">
        {summary}
      </p>
      {/* What every save control points at: touch and screen-reader users never
          see a tooltip, so the per-browser limit is said, not hovered. */}
      <p id={`${ids}-saved-hint`} className="sr-only">Saved calls are kept in this browser only.</p>

      {/* ---- Board ------------------------------------------------------- */}
      {loading ? (
        <BoardSkeleton />
      ) : loadFailed ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-triangle-exclamation"
          title="Could not load calls and conferences"
          message="The board did not load. Your saved calls are still kept in this browser."
          action={<Button variant="outline" onClick={load}>Try again</Button>}
        />
      ) : items.length === 0 ? (
        <EmptyState
          framed
          icon="fa-bullhorn"
          title="No calls posted yet"
          message={
            canPost
              ? "Post the first internal call, conference deadline or funding window, and it appears here for everyone."
              : "RDCO, KTTO and advisers post calls here as they open. Check back soon."
          }
          action={postButton || undefined}
        />
      ) : groups.length === 0 ? (
        <EmptyState
          framed
          icon={savedOnly ? "fa-bookmark" : "fa-magnifying-glass"}
          title={savedOnly && savedOnBoard === 0 ? "Nothing saved yet" : "Nothing matches these filters"}
          message={
            savedOnly && savedOnBoard === 0
              ? "Use the bookmark on a call to keep it here. Saved calls stay in this browser only."
              : "Try another type, or clear the search."
          }
          action={<Button variant="outline" onClick={clearFilters}>Clear filters</Button>}
        />
      ) : (
        <div className="space-y-section-lg">
          {groups.map((group) => (
            <section key={group.id} aria-labelledby={`${ids}-${group.id}`}>
              <h2
                id={`${ids}-${group.id}`}
                className="flex items-baseline gap-2 text-heading font-semibold text-stone-900 mb-3"
              >
                {group.title}
                <span className="text-small font-normal text-stone-600 tabular-nums">
                  {group.items.length} {group.items.length === 1 ? "call" : "calls"}
                </span>
              </h2>
              <ol
                className={cn(
                  "bg-white rounded-xl border border-stone-200 divide-y divide-stone-200",
                  group.id === "closed" && "bg-stone-50",
                )}
              >
                {group.items.map((o) => (
                  <li key={o.id}>
                    <OpportunityRow
                      opportunity={o}
                      saved={savedSet.has(o.id)}
                      savedHintId={`${ids}-saved-hint`}
                      icsBusy={icsBusy === o.id}
                      icsFailed={icsFailed === o.id}
                      onToggleSave={() => handleToggleSave(o.id)}
                      onDownloadIcs={() => void handleDownloadIcs(o)}
                      onEdit={() => setFormTarget(o)}
                      onDelete={() => { setDeleteError(null); setDeleting(o); }}
                    />
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}

      {formTarget !== null && (
        <OpportunityFormDialog
          opportunity={formTarget === "new" ? null : formTarget}
          onClose={() => setFormTarget(null)}
          onSaved={handleSaved}
        />
      )}

      <ConfirmDialog
        open={deleting !== null}
        title="Delete this call?"
        message={
          deleting
            ? `"${deleting.title}" will be removed from the board for everyone. This cannot be undone.`
            : ""
        }
        confirmLabel="Delete call"
        danger
        confirming={deleteBusy}
        error={deleteError}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

/** Rows shaped like the board's own, so the page does not jump when it loads. */
function BoardSkeleton() {
  const [announce, setAnnounce] = useState(false);
  // Filled on the next tick so screen readers hear the change (see Skeleton).
  useEffect(() => setAnnounce(true), []);

  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{announce ? "Loading calls and conferences…" : ""}</span>
      <div aria-hidden="true">
        <div className="h-5 w-48 rounded bg-stone-200 mb-3 animate-pulse motion-reduce:animate-none" />
        <div className="bg-white rounded-xl border border-stone-200 divide-y divide-stone-200">
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex gap-4 p-card-compact md:p-card">
              <div className="w-14 sm:w-16 h-20 shrink-0 rounded-lg bg-stone-100 animate-pulse motion-reduce:animate-none" />
              <div className="flex-1 space-y-2.5 pt-1">
                <div className="h-3 w-28 rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
                <div className="h-5 w-3/4 rounded bg-stone-200 animate-pulse motion-reduce:animate-none" />
                <div className="h-3 w-1/2 rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
                <div className="h-3 w-5/6 rounded bg-stone-100 animate-pulse motion-reduce:animate-none" />
              </div>
              <div className="hidden sm:block w-28 h-7 rounded-full bg-stone-100 animate-pulse motion-reduce:animate-none" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
