import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/shared/EmptyState";
import { ReadFailedState } from "@/components/shared/ReadFailedState";
import { LoadingRegion } from "@/components/ui/LoadingRegion";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { waitingHref } from "@/features/records/waitingOnYou";
import { usePublishHref } from "@/features/publish/publishLink";
import { cn, formatDate } from "@/lib/utils";
import type { HistoryItem } from "@/store/history.store";
import type { MyResearchItem } from "@/types/records";

import type { ResearchFilter } from "./researchSections";
import { SubmissionPanel, SubmissionRow } from "./SubmissionRow";

/** How many records Recent submissions shows before pointing at its tab. */
const RECENT_SHOWN = 4;
/** The side cards scroll (IR-1323); history is long, so it stops somewhere. */
const RECENTLY_OPENED_SHOWN = 20;

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
  /** The account's reading history (IR-756), most recent first. */
  history:     HistoryItem[];
  onOpenSubmissions: (filter: ResearchFilter) => void;
  /** A draft was deleted from its row (IR-1256); drop it. */
  onDeleted: (recordId: number) => void;
}

/**
 * My Library's Overview for an author (IR-1321, IR-1323). The left column is
 * their latest records. The right is two fixed-size cards, each scrolling its
 * own list: *Waiting on you*, the one place for what the author must act on
 * and the one counter on the page, then *Recently opened* (*Continue reading*
 * left in IR-1324). On a phone the cards come first, *Waiting on you* on top.
 */
export function LibraryOverview({
  research, loading, failed, interrupted = false, onRetry, history, onOpenSubmissions, onDeleted,
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

  return (
    <div className="grid gap-section-lg lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start">
      <div className="min-w-0 space-y-section lg:col-start-2 lg:row-start-1">
        <WaitingOnYou waiting={waiting} loading={loading} failed={failed} />

        <SideCard id="overview-opened" title="Recently opened" height="h-64">
          {recentlyOpened.length === 0 ? (
            <p className="text-small text-stone-600">Papers you open appear here.</p>
          ) : (
            <ul className="space-y-3">
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
          )}
        </SideCard>
      </div>

      <section aria-labelledby="overview-recent" className="min-w-0 lg:col-start-1 lg:row-start-1">
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
    </div>
  );
}

/**
 * One of the Overview's side cards (IR-1323): a fixed rectangle whose heading
 * and footer stay put while its list scrolls inside it, so a long list never
 * pushes the next card down.
 */
function SideCard({ id, title, height, accent = false, badge, footer, children }: {
  id: string;
  title: string;
  /** The card's fixed height, a Tailwind class. */
  height: string;
  /** *Waiting on you* with something in it: maroon heading and edge. */
  accent?: boolean;
  badge?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      aria-labelledby={id}
      className={cn(
        "flex min-w-0 flex-col rounded-card border p-card-compact",
        height,
        accent ? "border-brand/40 bg-surface" : "border-stone-200 bg-white",
      )}
    >
      <div className="flex shrink-0 items-center gap-2">
        <h2 id={id} className={cn("font-display text-title font-semibold", accent ? "text-brand" : "text-stone-900")}>
          {title}
        </h2>
        {badge}
      </div>
      <div className="mt-3 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 scrollbar-thin">
        {children}
      </div>
      {footer && <div className="mt-2 shrink-0">{footer}</div>}
    </section>
  );
}

/**
 * The first side card (IR-1321, IR-1323): each paper waiting on the author,
 * in the server's words, with one link per open request to where it is
 * answered. All of them, scrolling inside the card. It says nothing is
 * waiting only once the list has loaded, so a slow or failed read never
 * claims the author is clear.
 */
function WaitingOnYou({ waiting, loading, failed }: {
  waiting: MyResearchItem[];
  loading: boolean;
  failed: boolean;
}) {
  const any = waiting.length > 0;
  return (
    <SideCard
      id="overview-waiting"
      title="Waiting on you"
      height="h-96"
      badge={any && (
        <span className="rounded-full border border-brand px-2 text-label font-semibold tabular-nums text-brand">
          {waiting.length}
          <span className="sr-only"> {waiting.length === 1 ? "record" : "records"}</span>
        </span>
      )}
    >
      {loading ? (
        <div className="h-24 rounded-control bg-stone-100 motion-safe:animate-pulse" aria-hidden />
      ) : failed ? (
        <p className="text-small text-stone-600">Couldn’t check what is waiting on you. Your research list says why.</p>
      ) : !any ? (
        <p className="flex items-start gap-2 text-small text-stone-600">
          <i className="fas fa-circle-check mt-0.5 text-stone-500" aria-hidden />
          <span>Nothing needs your action. When a reviewer asks you for changes, it appears here.</span>
        </p>
      ) : (
        <ul className="divide-y divide-stone-200 border-t border-stone-200">
          {waiting.map((item) => (
            <li key={item.id} className="py-3 last:pb-0">
              <Link
                to={`/records/${item.id}`}
                className={cn("break-words rounded-control font-display text-heading font-semibold leading-snug text-stone-900 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
              >
                {item.title}
              </Link>
              <p className="mt-0.5 text-small text-stone-700">{item.submitter_status.line}</p>
              {/* One short link per paper (IR-1324): every request is answered on its
                  Documents tab, so the parties' requests share it. Their words stay for a screen reader. */}
              <Link
                to={waitingHref(item.id, item.submitter_status.waiting_on_you[0])}
                className={cn("-mx-1 mt-1 inline-flex min-h-8 items-center gap-1.5 rounded-control px-1 text-small font-semibold text-brand underline-offset-2 hover:underline", COLOUR_TRANSITION, FOCUS_RING)}
              >
                Submit documents
                <span className="sr-only"> ({item.submitter_status.waiting_on_you.map((r) => r.label).join("; ")}, {item.title})</span>
                <i className="fas fa-arrow-right text-label" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </SideCard>
  );
}
