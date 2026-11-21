import { useMemo } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { formatAuthorList, recordYearLabel } from "@/features/discover/discoverUtils";
import { waitingHref } from "@/features/records/waitingOnYou";
import { cn, formatDate } from "@/lib/utils";
import type { HistoryItem } from "@/store/history.store";
import { sortedItems, type LibraryFolder, type LibraryItem } from "@/store/library.store";
import type { MyResearchItem } from "@/types/records";

import type { LibraryView } from "./ReadingPanel";
import type { ResearchFilter } from "./researchSections";
import { SubmissionPanel, SubmissionRow } from "./SubmissionRow";

/** How many records each Overview list shows before pointing at its tab. */
const WAITING_SHOWN = 3;
const RECENT_SHOWN = 4;
const SHELF_SHOWN = 2;
const RECENTLY_OPENED_SHOWN = 3;

const LINK_TEXT = cn(
  "inline-flex min-h-9 items-center gap-2 rounded-control px-2 text-small font-semibold text-brand hover:bg-stone-100",
  COLOUR_TRANSITION,
  FOCUS_RING,
);

const isWaiting = (item: MyResearchItem) => item.submitter_status.waiting_on_you.length > 0;

interface LibraryOverviewProps {
  research:    MyResearchItem[];
  loading:     boolean;
  failed:      boolean;
  /** The read timed out (IR-906): Retry, not a refusal. */
  interrupted?: boolean;
  onRetry:     () => void;
  library:     Record<number, LibraryItem>;
  /** The account's reading history (IR-756), most recent first. */
  history:     HistoryItem[];
  /** The reader's own folders, which follow the account (IR-572). */
  folders:     LibraryFolder[];
  onOpenSubmissions: (filter: ResearchFilter) => void;
  onOpenSaved: (view: LibraryView) => void;
  /** A draft was deleted from its row (IR-1256); drop it. */
  onDeleted: (recordId: number) => void;
}

/**
 * My Library's Overview for an author: what is waiting on them, their latest
 * records, and the reading they are in the middle of. Every line is a server
 * fact, said as such; no counter appears
 * except beside Waiting on you, where each one is a thing to do.
 */
export function LibraryOverview({
  research, loading, failed, interrupted = false, onRetry, library, history, folders, onOpenSubmissions, onOpenSaved, onDeleted,
}: LibraryOverviewProps) {
  const waiting = useMemo(() => research.filter(isWaiting), [research]);
  /* Only papers the reader can still read; an unavailable entry has no title to show. */
  const recentlyOpened = useMemo(
    () => history.flatMap((v) => (v.available && v.record && v.viewedAt ? [{ record: v.record, viewedAt: v.viewedAt }] : [])).slice(0, RECENTLY_OPENED_SHOWN),
    [history],
  );
  const recent = useMemo(
    () => [...research].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, RECENT_SHOWN),
    [research],
  );
  const reading = useMemo(
    () => sortedItems(library).filter((i) => i.readingStatus === "reading" && i.available && i.record).slice(0, SHELF_SHOWN),
    [library],
  );

  return (
    <div className="space-y-section-lg">
      {waiting.length > 0 && (
        <section aria-labelledby="overview-waiting" className="rounded-card border border-stone-300 bg-surface p-card-compact md:p-card">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand text-white" aria-hidden>
                <i className="fas fa-hourglass-half text-small" />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <h2 id="overview-waiting" className="font-display text-title font-semibold text-brand">Waiting on you</h2>
                  <span className="rounded-full bg-brand px-2 text-label font-semibold tabular-nums text-white">
                    {waiting.length}
                    <span className="sr-only"> {waiting.length === 1 ? "record" : "records"}</span>
                  </span>
                </div>
                <p className="text-small text-brand-dark">A reviewer needs something from you before review can go on.</p>
              </div>
            </div>
            {waiting.length > WAITING_SHOWN && (
              <button type="button" onClick={() => onOpenSubmissions("waiting")} className={LINK_TEXT}>
                Show all <i className="fas fa-arrow-right text-label" aria-hidden />
              </button>
            )}
          </div>

          <ul className="mt-4 divide-y divide-stone-200 border-t border-stone-200">
            {waiting.slice(0, WAITING_SHOWN).map((item) => (
              <li key={item.id} className="flex flex-col gap-3 py-3 md:flex-row md:items-center md:justify-between">
                <div className="min-w-0">
                  <Link
                    to={`/records/${item.id}`}
                    className={cn("rounded-control font-display text-heading font-semibold text-stone-900 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
                  >
                    {item.title}
                  </Link>
                  <p className="text-small text-stone-700">{item.submitter_status.line}</p>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {item.submitter_status.waiting_on_you.map((request) => (
                    <Link
                      key={`${request.kind}-${request.party}`}
                      to={waitingHref(item.id, request)}
                      className={cn(PILL_SECONDARY, "min-h-9 bg-white px-4", FOCUS_RING)}
                    >
                      {request.action_label}
                      <span className="sr-only"> ({request.label}, {item.title})</span>
                      <i className="fas fa-arrow-right text-label" aria-hidden />
                    </Link>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-section-lg lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <section aria-labelledby="overview-recent" className="min-w-0">
          <div className="mb-3 flex items-end justify-between gap-3">
            <div>
              <h2 id="overview-recent" className="font-display text-title font-semibold text-stone-900">Recent submissions</h2>
              <p className="text-small text-stone-600">Your latest records, by when they last changed.</p>
            </div>
            {research.length > 0 && (
              <button type="button" onClick={() => onOpenSubmissions("all")} className={LINK_TEXT}>
                All submissions <i className="fas fa-arrow-right text-label" aria-hidden />
              </button>
            )}
          </div>

          {loading ? (
            <LoadingRegion label="Loading your research…" onRetry={onRetry}>
              <div className="h-64 rounded-card border border-stone-200 bg-white motion-safe:animate-pulse" />
            </LoadingRegion>
          ) : failed ? (
            <ReadFailedState
              interrupted={interrupted}
              what="research list"
              title="Could not load your research"
              lead="Nothing was changed."
              onRetry={onRetry}
            />
          ) : recent.length === 0 ? (
            <EmptyState
              framed
              icon="fa-feather-pointed"
              title="You haven’t published anything yet"
              message="Publish a paper and it will appear here, grouped by who is reviewing it."
              action={<Link to="/?publish=new" className={cn(PILL_PRIMARY, FOCUS_RING)}>Publish</Link>}
            />
          ) : (
            <SubmissionPanel>
              {recent.map((item) => <SubmissionRow key={item.id} item={item} brief onDeleted={onDeleted} />)}
            </SubmissionPanel>
          )}
        </section>

        <section aria-labelledby="overview-shelf" className="rounded-card border border-stone-200 bg-white p-card-compact md:p-card">
          <h2 id="overview-shelf" className="font-display text-title font-semibold text-stone-900">Reading shelf</h2>
          <p className="text-small text-stone-600">Saved papers follow your account.</p>

          <h3 className="mt-5 text-label font-semibold text-stone-600">Continue reading</h3>
          {reading.length === 0 ? (
            <p className="mt-1 text-small text-stone-600">
              Mark a saved paper <span className="font-semibold text-stone-800">Reading</span> and it waits here.
            </p>
          ) : (
            <ul className="mt-2 space-y-3">
              {reading.map(({ record }) => record && (
                <li key={record.id} className="flex gap-3">
                  <span className="grid h-14 w-11 shrink-0 place-items-center rounded-control bg-stone-100 text-stone-600 ring-1 ring-stone-200" aria-hidden>
                    <i className="fas fa-book-open text-small" />
                  </span>
                  <div className="min-w-0">
                    <Link
                      to={`/records/${record.id}`}
                      className={cn("break-words rounded-control font-display text-heading font-semibold leading-snug text-stone-900 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
                    >
                      {record.title}
                    </Link>
                    <p className="break-words text-label text-stone-600">
                      {formatAuthorList(record.authors, 2)} · {recordYearLabel(record)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {recentlyOpened.length > 0 && (
            <div className="mt-5 border-t border-stone-200 pt-4">
              <h3 className="text-label font-semibold text-stone-600">Recently opened</h3>
              <ul className="mt-2 space-y-2">
                {recentlyOpened.map(({ record, viewedAt }) => (
                  <li key={record.id}>
                    <Link
                      to={`/records/${record.id}`}
                      className={cn("block break-words rounded-control text-small font-semibold text-stone-800 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
                    >
                      {record.title}
                    </Link>
                    <p className="text-label text-stone-500">Opened {formatDate(viewedAt)}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {folders.length > 0 && (
            <div className="mt-5 border-t border-stone-200 pt-4">
              <h3 className="text-label font-semibold text-stone-600">Your folders</h3>
              <ul className="mt-1 -mx-2">
                {folders.slice(0, 4).map((f) => (
                  <li key={f.id}>
                    <button
                      type="button"
                      onClick={() => onOpenSaved({ kind: "folder", id: f.id })}
                      className={cn("flex min-h-9 w-full items-center gap-3 rounded-control px-2 text-left text-small text-stone-700 hover:bg-stone-50", COLOUR_TRANSITION, FOCUS_RING)}
                    >
                      <i className="fas fa-folder w-4 text-center text-stone-500" aria-hidden />
                      <span className="min-w-0 flex-1 break-words">{f.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 border-t border-stone-200 pt-3">
            <button type="button" onClick={() => onOpenSaved({ kind: "saved" })} className={cn(LINK_TEXT, "-mx-2 w-[calc(100%+1rem)] justify-between")}>
              Open saved papers <i className="fas fa-arrow-right text-label" aria-hidden />
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
