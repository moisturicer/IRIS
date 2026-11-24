import { useMemo } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { formatAuthorList, recordYearLabel } from "@/features/discover/discoverUtils";
import { waitingHref } from "@/features/records/waitingOnYou";
import { usePublishHref } from "@/features/publish/publishLink";
import { cn, formatDate } from "@/lib/utils";
import type { HistoryItem } from "@/store/history.store";
import { sortedItems, type LibraryItem } from "@/store/library.store";
import type { MyResearchItem } from "@/types/records";

import type { LibraryView } from "./ReadingPanel";
import type { ResearchFilter } from "./researchSections";
import { SubmissionPanel, SubmissionRow } from "./SubmissionRow";

/** How many records each Overview list shows before pointing at its tab. */
const WAITING_SHOWN = 4;
const RECENT_SHOWN = 4;
const SHELF_SHOWN = 3;
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
  onOpenSubmissions: (filter: ResearchFilter) => void;
  onOpenSaved: (view: LibraryView) => void;
  /** A draft was deleted from its row (IR-1256); drop it. */
  onDeleted: (recordId: number) => void;
}

/**
 * My Library's Overview for an author (IR-1321). The right column is
 * *Waiting on you*, the one place for what the author must act on, with the
 * one counter on the page. The left holds their latest records, then the
 * reading they are in the middle of. On a phone *Waiting on you* comes first.
 */
export function LibraryOverview({
  research, loading, failed, interrupted = false, onRetry, library, history, onOpenSubmissions, onOpenSaved, onDeleted,
}: LibraryOverviewProps) {
  const publishHref = usePublishHref();
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
    <div className="grid gap-section-lg lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <WaitingOnYou
        waiting={waiting}
        loading={loading}
        failed={failed}
        onShowAll={() => onOpenSubmissions("waiting")}
      />

      <div className="min-w-0 space-y-section-lg lg:col-start-1 lg:row-start-1">
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
              action={<Link to={publishHref("new")} className={cn(PILL_PRIMARY, FOCUS_RING)}>Publish</Link>}
            />
          ) : (
            <SubmissionPanel>
              {recent.map((item) => <SubmissionRow key={item.id} item={item} brief onDeleted={onDeleted} />)}
            </SubmissionPanel>
          )}
        </section>

        <div className="grid gap-x-8 gap-y-section border-t border-stone-200 pt-section md:grid-cols-2">
          <section aria-labelledby="overview-reading" className="min-w-0">
            <h2 id="overview-reading" className="font-display text-heading font-semibold text-stone-900">Continue reading</h2>
            {reading.length === 0 ? (
              <p className="mt-1 text-small text-stone-600">
                Mark a saved paper <span className="font-semibold text-stone-800">Reading</span> and it waits here.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {reading.map(({ record }) => record && (
                  <li key={record.id} className="flex gap-3">
                    <span className="grid h-12 w-10 shrink-0 place-items-center rounded-control bg-stone-100 text-stone-600 ring-1 ring-stone-200" aria-hidden>
                      <i className="fas fa-book-open text-small" />
                    </span>
                    <div className="min-w-0">
                      <Link
                        to={`/records/${record.id}`}
                        className={cn("break-words rounded-control font-display text-body font-semibold leading-snug text-stone-900 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
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
            <button type="button" onClick={() => onOpenSaved({ kind: "saved" })} className={cn(LINK_TEXT, "mt-3 -mx-2")}>
              Open saved papers <i className="fas fa-arrow-right text-label" aria-hidden />
            </button>
          </section>

          {recentlyOpened.length > 0 && (
            <section aria-labelledby="overview-opened" className="min-w-0">
              <h2 id="overview-opened" className="font-display text-heading font-semibold text-stone-900">Recently opened</h2>
              <ul className="mt-3 space-y-3">
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
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * The Overview's right column (IR-1321): each paper waiting on the author,
 * in the server's words, with one link per open request to where it is
 * answered. It says nothing is waiting only once the list has loaded, so a
 * slow or failed read never claims the author is clear.
 */
function WaitingOnYou({ waiting, loading, failed, onShowAll }: {
  waiting: MyResearchItem[];
  loading: boolean;
  failed: boolean;
  onShowAll: () => void;
}) {
  const any = waiting.length > 0;
  return (
    <section
      aria-labelledby="overview-waiting"
      className={cn(
        "min-w-0 rounded-card border p-card-compact lg:col-start-2 lg:row-start-1",
        any ? "border-brand/40 bg-surface" : "border-stone-200 bg-white",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 id="overview-waiting" className={cn("font-display text-title font-semibold", any ? "text-brand" : "text-stone-900")}>
            Waiting on you
          </h2>
          {any && (
            <span className="rounded-full border border-brand px-2 text-label font-semibold tabular-nums text-brand">
              {waiting.length}
              <span className="sr-only"> {waiting.length === 1 ? "record" : "records"}</span>
            </span>
          )}
        </div>
        {waiting.length > WAITING_SHOWN && (
          <button type="button" onClick={onShowAll} className={LINK_TEXT}>
            Show all <i className="fas fa-arrow-right text-label" aria-hidden />
          </button>
        )}
      </div>

      {loading ? (
        <div className="mt-4 h-24 rounded-control bg-stone-100 motion-safe:animate-pulse" aria-hidden />
      ) : failed ? (
        <p className="mt-2 text-small text-stone-600">Couldn’t check what is waiting on you. Your research list says why.</p>
      ) : !any ? (
        <p className="mt-2 flex items-start gap-2 text-small text-stone-600">
          <i className="fas fa-circle-check mt-0.5 text-stone-500" aria-hidden />
          <span>Nothing needs your action. When a reviewer asks you for changes, it appears here.</span>
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-stone-200 border-t border-stone-200">
          {waiting.slice(0, WAITING_SHOWN).map((item) => (
            <li key={item.id} className="py-3 last:pb-0">
              <Link
                to={`/records/${item.id}`}
                className={cn("break-words rounded-control font-display text-heading font-semibold leading-snug text-stone-900 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
              >
                {item.title}
              </Link>
              <p className="mt-0.5 text-small text-stone-700">{item.submitter_status.line}</p>
              <div className="mt-2 flex flex-wrap gap-2">
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
      )}
    </section>
  );
}
