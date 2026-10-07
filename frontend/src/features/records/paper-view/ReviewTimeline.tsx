import { useEffect, useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { RecordTracker } from "@/types/records";

import { RailHeading } from "./headings";
import { timelineEntries, type TimelineEntry, type TimelineKind } from "./timelineEntries";

/** A glyph per kind of entry, beside its words, never instead of them. */
const KIND_ICON: Record<TimelineKind, string> = {
  routing: "fa-route",
  review: "fa-clipboard-check",
  revision: "fa-arrow-rotate-left",
  revision_resolved: "fa-paper-plane",
  document_request: "fa-file-circle-plus",
};

/**
 * The Review section's timeline (IR-412; spec §4.7): what has happened in the
 * review, oldest first, each entry saying who did what, as which party, and
 * when. Built from `GET /records/<id>/tracker/` alone (`timelineEntries.ts`).
 *
 * It is a history, so it marks nothing as current. Where the record is now
 * is the party strip's job, on Overview's rail; this list never renders a
 * party -- Intake included, which ADR-032 retires -- as the present step.
 *
 * The host remounts it (a new `key`) when something it shows has changed.
 */
export function ReviewTimeline({ recordId }: { recordId: number }) {
  const headingId = useId();
  const [data, setData] = useState<RecordTracker | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    recordsApi
      .tracker(recordId)
      .then(({ data: payload }) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, attempt]);

  const entries = data ? timelineEntries(data) : [];

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <RailHeading id={headingId}>Timeline</RailHeading>

      {failed ? (
        <div className="space-y-2">
          <p role="alert" className="text-small text-stone-700">
            Could not load the review timeline.
          </p>
          <button
            type="button"
            onClick={() => setAttempt((n) => n + 1)}
            className={cn("text-small font-semibold text-brand hover:underline min-h-11", FOCUS_RING)}
          >
            Try again
          </button>
        </div>
      ) : !data ? (
        <div aria-hidden className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-10 rounded-lg bg-stone-100 animate-pulse motion-reduce:animate-none" />
          ))}
        </div>
      ) : (
        <>
          {data.routing_recorded_from && (
            <p className="text-2xs text-stone-600">
              Routing recorded from {formatDate(data.routing_recorded_from)}.
            </p>
          )}
          {entries.length === 0 ? (
            <p className="text-small text-stone-600">Nothing has happened in this review yet.</p>
          ) : (
            <ol aria-label="Review timeline" className="relative space-y-4 border-l border-stone-200 ml-2">
              {entries.map((entry) => (
                <TimelineItem key={entry.key} entry={entry} />
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}

function TimelineItem({ entry }: { entry: TimelineEntry }) {
  const byline = [entry.actor, entry.party].filter(Boolean) as string[];

  return (
    <li className="relative pl-6">
      <span
        aria-hidden
        className="absolute -left-3 top-0 w-6 h-6 rounded-full bg-white ring-1 ring-stone-200 flex items-center justify-center"
      >
        <i className={cn("fas text-2xs text-stone-600", KIND_ICON[entry.kind])} />
      </span>
      <div className="flex items-baseline gap-x-2 gap-y-1 flex-wrap">
        <p className="text-small font-semibold text-stone-900">{entry.act}</p>
        {entry.status && (
          <span className="px-1.5 py-0.5 rounded bg-stone-100 text-2xs font-semibold text-stone-700">
            {entry.status}
          </span>
        )}
      </div>
      <p className="text-2xs text-stone-600 mt-0.5">
        {byline.map((part, i) => (
          <span key={i} className={cn(i === 0 && entry.actor && "font-semibold text-stone-700")}>
            {i > 0 && " · "}
            {part}
          </span>
        ))}
        {byline.length > 0 && " · "}
        {entry.at ? <time dateTime={entry.at}>{formatDate(entry.at)}</time> : "Date not recorded"}
      </p>
      {entry.note && (
        <p className="text-small text-stone-700 leading-relaxed mt-1 break-words">“{entry.note}”</p>
      )}
      {/* By position: two items can read the same (one label, one state). */}
      {entry.details.map((line, i) => (
        <p key={i} className="text-2xs text-stone-600 mt-0.5 break-words">
          {line}
        </p>
      ))}
    </li>
  );
}
