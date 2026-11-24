import { useCallback, useEffect, useId, useMemo, useState } from "react";

import { opportunitiesApi } from "@/api/opportunities";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import { PageHeader } from "@/components/layout/PageHeader";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button, ButtonLink } from "@/components/ui/Button";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { SkeletonBlock } from "@/components/ui/Skeleton";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { useSavedCallsStore } from "@/store/savedCalls.store";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import type { Opportunity, OpportunityType } from "@/types/opportunities";

import { RdcoNoteDialog } from "@/features/admin/RdcoNoteDialog";

import { posterOf, useDeleteCall, useFeaturedToggle, useReportCallFailure } from "./callActions";
import { OpportunityFormDialog } from "./OpportunityFormDialog";
import { OpportunityRow } from "./OpportunityRow";
import {
  DEADLINE_GROUPS,
  OPPORTUNITY_TYPES,
  areaNames,
  byBoardOrder,
  papersClosed,
  deadlineGroup,
  matchesQuery,
} from "./opportunityUtils";
import { SearchGlyph } from "@/components/brand/IrisBrand";
import { SELECTED } from "@/components/ui/highlightRoles";

/** A filter chip, as My Reviews draws them: soft maroon when on. */
function chipClass(on: boolean) {
  return cn(
    "inline-flex shrink-0 items-center gap-1.5 min-h-11 lg:min-h-9 px-3 rounded-full border text-small font-medium whitespace-nowrap",
    COLOUR_TRANSITION,
    FOCUS_RING,
    on ? SELECTED : "border-stone-200 bg-white text-stone-700 hover:border-stone-400",
    "disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:border-stone-200",
  );
}

/** Which sheet is open: none, a new call, or an existing one being edited. */
type FormTarget = null | "new" | Opportunity;

/**
 * Calls & Conferences: a board of calls for papers (IR-121, IR-530; ADR-050,
 * IR-764).
 *
 * The one question it answers is "where can I still send a paper, and by
 * when", so the board is a single column grouped by how soon papers close, in
 * date order inside each group; a Featured call is starred, never moved. Calls
 * whose submissions have closed stay in a last group until their event is
 * over, when the server takes them off the board.
 *
 * RDCO and Advisers post here, and change what they posted. The page offers
 * that only when the server says so (`can_post`, `can_edit`, `can_feature`);
 * the API is the boundary either way. An Adviser's new or edited Call waits
 * for RDCO, so it leaves the board and a toast says where it went.
 *
 * Feedback on an action is a toast, never a box that grows inside the board.
 *
 * Saves follow the account (IR-766, `store/savedCalls.store.ts`), and the
 * Saved filter shows the saved Calls still on the board; My Library keeps
 * every saved Call, Over ones included. There is no in-app reminder: the
 * calendar action hands over an .ics file the viewer's own calendar keeps.
 */
export function CallsAndConferencesPage() {
  const addToast = useUIStore((s) => s.addToast);
  const ids = useId();

  const [items,    setItems]    = useState<Opportunity[]>([]);
  const [canPost,  setCanPost]  = useState(false);
  const [canFeature, setCanFeature] = useState(false);
  const [loading,  setLoading]  = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const [activeType, setActiveType] = useState<OpportunityType | null>(null);
  const [query,      setQuery]      = useState("");
  /** An Area's name, or "" for every Area. */
  const [activeArea, setActiveArea] = useState("");
  const [savedOnly,  setSavedOnly]  = useState(false);
  const savedItems   = useSavedCallsStore((s) => s.items);
  const savedLoad    = useSavedCallsStore((s) => s.load);
  const ensureSaved  = useSavedCallsStore((s) => s.ensureLoaded);
  const saveCall     = useSavedCallsStore((s) => s.save);
  const unsaveCall   = useSavedCallsStore((s) => s.unsave);

  const [icsBusy,   setIcsBusy]   = useState<number | null>(null);

  const [formTarget, setFormTarget] = useState<FormTarget>(null);
  /** The Adviser's Call RDCO is removing with a reason (IR-765). */
  const [removing,   setRemoving]   = useState<Opportunity | null>(null);


  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
    opportunitiesApi
      .board()
      .then((board) => {
        if (cancelled) return;
        // Read the account's saves afresh with each board, so a save made on
        // another device shows here too.
        void ensureSaved(true);
        setItems([...board.items].sort(byBoardOrder));
        setCanPost(board.can_post);
        setCanFeature(board.can_feature);
      })
      .catch(() => { if (!cancelled) setLoadFailed(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ensureSaved]);

  useEffect(() => load(), [load]);

  // A decision on the reader's own Call says `calls`, and anyone's board
  // catches up when the tab is shown again (IR-1289). Quiet: the board stays,
  // and a failed read keeps it.
  const refresh = useCallback(() => {
    opportunitiesApi.board()
      .then((board) => {
        setItems([...board.items].sort(byBoardOrder));
        setCanPost(board.can_post);
        setCanFeature(board.can_feature);
      })
      .catch(() => { /* keep the board; focus or the next hint retries */ });
  }, []);
  useLiveRefresh(["calls"], refresh);

  // ---- Filtering ---------------------------------------------------------

  /**
   * The saved Calls on the board: the account's list once it has loaded, and
   * until then (or if it can't load) the server's `is_saved` on each Call, so
   * a failed read never shows every bookmark as unsaved.
   */
  const savedSet = useMemo(
    () => savedLoad === "ready"
      ? new Set(Object.keys(savedItems).map(Number))
      : new Set(items.filter((o) => o.is_saved).map((o) => o.id)),
    [savedLoad, savedItems, items],
  );
  /** Saved calls that are on the board now, which is what the Saved chip counts. */
  const savedOnBoard = useMemo(() => items.filter((o) => savedSet.has(o.id)).length, [items, savedSet]);

  /** Every Area on the board, for the Area filter. */
  const areas = useMemo(() => areaNames(items), [items]);

  /** Everything the search, Area and saved filters keep, before the type filter. */
  const searched = useMemo(
    () => items.filter((o) =>
      matchesQuery(o, query)
      && (!activeArea || (o.area_names ?? []).includes(activeArea))
      && (!savedOnly || savedSet.has(o.id))),
    [items, query, activeArea, savedOnly, savedSet],
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

  const openCount = useMemo(() => items.filter((o) => !papersClosed(o)).length, [items]);
  const filtered  = activeType !== null || query.trim() !== "" || activeArea !== "" || savedOnly;

  const clearFilters = () => {
    setActiveType(null);
    setQuery("");
    setActiveArea("");
    setSavedOnly(false);
  };

  // ---- Actions -----------------------------------------------------------

  /** Save or unsave; the store shows it at once and rolls back with a toast on failure. */
  const handleToggleSave = (o: Opportunity) => {
    if (savedSet.has(o.id)) void unsaveCall(o);
    else void saveCall(o);
  };

  const handleDownloadIcs = async (o: Opportunity) => {
    setIcsBusy(o.id);
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
      // A toast, not a line inside the row: nothing on the board moves. It
      // names the call and stays until the reader acts on it or dismisses it.
      addToast({
        type: "error",
        message: `Could not build the calendar file for ${o.title}. Try again.`,
        persist: true,
        action: { label: "Try again", onClick: () => void handleDownloadIcs(o) },
      });
    } finally {
      setIcsBusy(null);
    }
  };

  const handleSaved = (saved: Opportunity, created: boolean) => {
    // Only a confirmed Call is on the board. An Adviser's post or edit waits
    // for RDCO (ADR-050 decisions 8 and 10), so it leaves the board, as a
    // reload would show, and the toast says where it went.
    const onBoard = saved.status === "confirmed";
    setItems((current) => {
      const others = current.filter((o) => o.id !== saved.id);
      return (onBoard ? [...others, saved] : others).sort(byBoardOrder);
    });
    setFormTarget(null);
    addToast(
      onBoard
        ? { type: "success", message: created ? "Call posted." : "Changes saved." }
        : { type: "info", message: "Call sent to RDCO. It appears on the board once RDCO confirms it." },
    );
  };

  const report = useReportCallFailure(load);
  /** Replace one Call with the server's copy, keeping the board's order; Featured never moves it. */
  const featured = useFeaturedToggle(
    (next) => setItems((current) => current.map((o) => (o.id === next.id ? next : o)).sort(byBoardOrder)),
    report,
  );
  const deletion = useDeleteCall((gone) => setItems((current) => current.filter((o) => o.id !== gone.id)), report);

  // ---- Render ------------------------------------------------------------

  const postButton = canPost && (
    <button type="button" onClick={() => setFormTarget("new")} className={cn(PILL_PRIMARY, FOCUS_RING)}>
      <i className="fas fa-plus" aria-hidden="true" />
      Post a call
    </button>
  );

  // A poster's own Calls, waiting or rejected ones included, are on My Calls (IR-765).
  const headerActions = canPost && (
    <div className="flex flex-wrap items-center gap-2">
      <ButtonLink to="/opportunities/mine" variant="outline" size="sm">My calls</ButtonLink>
      {postButton}
    </div>
  );

  const ready = !loading && !loadFailed;

  // An empty board has nothing to search, filter or count (audit US-13):
  // its empty state says so instead.
  const emptyBoard = ready && items.length === 0;
  // The controls appear with the rows, once the board is known to have calls
  // (IR-1314). Shown while loading, they flashed and then vanished whenever the
  // board turned out empty; after a failure there is nothing to filter either.
  const hasBoard = ready && items.length > 0;

  const summary = !ready || emptyBoard
    ? ""
    : filtered
      ? `Showing ${visible.length} of ${items.length} ${items.length === 1 ? "call" : "calls"}.`
      : `${openCount} ${openCount === 1 ? "call" : "calls"} accepting papers${items.length > openCount ? `, ${items.length - openCount} with submissions closed` : ""}.`;

  return (
    <div>
      <PageHeader
        title="Calls & Conferences"
        description="Calls for papers from conferences, journals and other venues, posted by RDCO and advisers. Soonest deadline first."
        actions={headerActions || undefined}
      />

      {/* ---- Search and filters ------------------------------------------ */}
      {/* Search first, in its own row under the title: it is the first thing
          a reader reaches for, and at the end of the chip row it was missed.
          The row appears with the board itself, so its counts are never
          a number IRIS does not know yet. */}
      {hasBoard && (
      <div className="space-y-3 mb-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="basis-full sm:basis-auto flex-1 min-w-0 sm:max-w-md">
            <Input
              id={`${ids}-search`}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search calls"
              aria-label="Search calls by title, location or Area"
              leading={<SearchGlyph className="h-3 w-3" />}
            />
          </div>
          {/* One width whatever the Areas are (IR-1313): it grew with the
              longest Area on the board. 18rem from `sm`, the row below it. That
              holds every Area IRIS has (the longest needs about 190px); an Area
              is typed by staff, up to 200 characters, so a longer one is clipped
              closed and read in full in the open list or on hover. */}
          <div className="w-full sm:w-auto">
            <Select
              id={`${ids}-area`}
              label="Area"
              inline
              size="sm"
              value={activeArea}
              onChange={(e) => setActiveArea(e.target.value)}
              title={activeArea || "All Areas"}
              className="sm:w-72"
            >
              <option value="">All Areas</option>
              {areas.map((name) => <option key={name} value={name}>{name}</option>)}
            </Select>
          </div>
          <button
            type="button"
            aria-pressed={savedOnly}
            onClick={() => setSavedOnly((v) => !v)}
            className={chipClass(savedOnly)}
          >
            <i className={cn(savedOnly ? "fas" : "far", "fa-bookmark text-3xs")} aria-hidden="true" />
            Saved
            <span className="tabular-nums opacity-80">{savedOnBoard}</span>
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
            className={chipClass(activeType === null)}
          >
            All
            <span className="tabular-nums opacity-80">{searched.length}</span>
          </button>
          {OPPORTUNITY_TYPES.map((t) => (
            <button
              key={t.id}
              type="button"
              aria-pressed={activeType === t.id}
              onClick={() => setActiveType(activeType === t.id ? null : t.id)}
              className={chipClass(activeType === t.id)}
            >
              <i className={cn("fas", t.icon, "text-3xs")} aria-hidden="true" />
              {t.label}
              <span className="tabular-nums opacity-80">{typeCounts.get(t.id) ?? 0}</span>
            </button>
          ))}
        </div>
      </div>
      )}

      {/* Always rendered, so a change to it is what a screen reader hears. */}
      <p role="status" aria-live="polite" className="text-small text-stone-600 min-h-5 mb-section">
        {summary}
      </p>

      {/* ---- Board ------------------------------------------------------- */}
      {loading ? (
        <BoardSkeleton />
      ) : loadFailed ? (
        <EmptyState
          framed
          tone="error"
          icon="fa-triangle-exclamation"
          title="Could not load calls and conferences"
          message="The board did not load. Your saved calls are safe in My Library."
          action={<Button variant="outline" onClick={load}>Try again</Button>}
        />
      ) : items.length === 0 ? (
        <EmptyState
          framed
          icon="fa-bullhorn"
          title="No calls posted yet"
          message={
            canPost
              ? "Post the first call for papers, from a conference, workshop, journal or book, and it appears here for everyone."
              : "RDCO and advisers post calls here as they open. Check back soon."
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
              ? "Use the bookmark on a call to keep it here and in My Library."
              : "Try another type or Area, or clear the search."
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
                  "bg-white rounded-card border border-stone-200 divide-y divide-stone-200",
                  group.id === "closed" && "bg-stone-50",
                )}
              >
                {group.items.map((o) => (
                  <li key={o.id}>
                    <OpportunityRow
                      opportunity={o}
                      saved={savedSet.has(o.id)}
                      icsBusy={icsBusy === o.id}
                      onToggleSave={() => handleToggleSave(o)}
                      onDownloadIcs={() => void handleDownloadIcs(o)}
                      onEdit={() => setFormTarget(o)}
                      onDelete={() => deletion.ask(o)}
                      onRemove={() => setRemoving(o)}
                      onToggleFeatured={() => void featured.toggle(o)}
                      featuring={featured.featuringId === o.id}
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
          canFeature={formTarget === "new" ? canFeature : formTarget.can_feature}
          onClose={() => setFormTarget(null)}
          onSaved={handleSaved}
        />
      )}

      {removing && (
        <RdcoNoteDialog
          kind="reason"
          title="Remove this call"
          submitLabel="Remove call"
          audience="Adviser"
          requester={posterOf(removing)}
          recordTitle={removing.title}
          intro="It leaves the board. The Adviser is told in-app, with your reason."
          send={(reason) => opportunitiesApi.removeWithReason(removing.id, reason)}
          onClose={() => setRemoving(null)}
          onDone={() => {
            const gone = removing;
            setItems((current) => current.filter((o) => o.id !== gone.id));
            setRemoving(null);
            addToast({ type: "success", message: `${gone.title} removed. Its Adviser is told why.` });
          }}
          // The reason stays typed for another try, unless the Call is gone.
          onFailure={(err) => (report(err, `Could not remove ${removing.title}.`).stale ? "close" : "keep")}
        />
      )}

      <ConfirmDialog
        open={deletion.deleting !== null}
        title="Delete this call?"
        message={
          deletion.deleting
            ? `"${deletion.deleting.title}" will be removed from the board for everyone. This cannot be undone.`
            : ""
        }
        confirmLabel="Delete call"
        danger
        confirming={deletion.busy}
        onConfirm={deletion.confirm}
        onCancel={deletion.cancel}
      />
    </div>
  );
}

/** Rows shaped like the board's own, so the page does not jump when it loads. */
function BoardSkeleton() {
  return (
    <LoadingRegion label="Loading calls and conferences…">
      <SkeletonBlock tone="strong" className="h-5 w-48 mb-3" />
      <div className="bg-white rounded-card border border-stone-200 divide-y divide-stone-200">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-4 p-card-compact md:p-card">
            <SkeletonBlock className="w-14 sm:w-16 h-20 shrink-0" />
            <div className="flex-1 space-y-2.5 pt-1">
              <SkeletonBlock className="h-3 w-28" />
              <SkeletonBlock tone="strong" className="h-5 w-3/4" />
              <SkeletonBlock className="h-3 w-1/2" />
              <SkeletonBlock className="h-3 w-5/6" />
            </div>
            <SkeletonBlock shape="pill" className="hidden sm:block w-28 h-7" />
          </div>
        ))}
      </div>
    </LoadingRegion>
  );
}
