import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { reviewsApi, type QueueFilter } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { PeerClearanceStrip } from "./PeerClearanceStrip";
import type { ReviewQueueRow } from "@/types/reviews";
import { cn } from "@/lib/utils";
import { isQueueFilter, waitLabel, waitTone } from "./queueFilters";

/**
 * The review queue -- one screen, three filters (IR-143).
 *
 * This replaces `PendingRecordsPage`, `ApprovedRecordsPage` and
 * `DeclinedRecordsPage`, which differed only by which endpoint they called and
 * showed Title / Type / Submitted / Review. A KTTO reviewer and an IERC
 * reviewer saw byte-identical rows: nothing said which clearance was theirs,
 * what the record was waiting for, whether anyone else had acted, or how long
 * it had sat. The server had always scoped the list correctly; the payload just
 * never said so, until IR-139 added the fields this screen reads.
 *
 * The filter lives in the URL, so a queue can be linked, bookmarked and
 * returned to with the back button rather than resetting to Pending.
 */

const FILTERS: { key: QueueFilter; label: string; icon: string }[] = [
  { key: "pending",  label: "Awaiting me", icon: "fa-hourglass-half" },
  { key: "approved", label: "Cleared",     icon: "fa-check" },
  { key: "declined", label: "Sent back",   icon: "fa-arrow-rotate-left" },
];

const EMPTY_COPY: Record<QueueFilter, { title: string; message: string }> = {
  pending:  { title: "Nothing awaiting you",
              message: "When a record reaches a stage you clear, it appears here." },
  approved: { title: "No cleared records yet",
              message: "Records you have cleared stay here as your decision history." },
  declined: { title: "Nothing sent back",
              message: "Records you returned for revision appear here until they are resubmitted." },
};

export default function ReviewQueuePage() {
  const [params, setParams] = useSearchParams();
  const raw = params.get("status");
  const filter: QueueFilter = isQueueFilter(raw) ? raw : "pending";

  const [rows, setRows] = useState<ReviewQueueRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    reviewsApi
      .queue(filter)
      .then(({ data }) => {
        if (!cancelled) setRows(data);
      })
      .catch(() => {
        // An empty queue and a failed request look identical if the error is
        // swallowed, and one of them is a reason to reload.
        if (!cancelled) setError("Could not load the queue.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filter]);

  const setFilter = (next: QueueFilter) => setParams(next === "pending" ? {} : { status: next });

  return (
    <div>
      <PageHeader
        title="Review Queue"
        description="Records at a stage you decide. Each row shows what it is waiting for and what the other offices have already done."
      />

      <div
        role="tablist"
        aria-label="Queue filter"
        className="flex flex-wrap gap-1 mb-4 border-b border-stone-200"
      >
        {FILTERS.map((f) => {
          const active = f.key === filter;
          return (
            <button
              key={f.key}
              role="tab"
              type="button"
              aria-selected={active}
              onClick={() => setFilter(f.key)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 text-[13px] font-semibold border-b-2 -mb-px transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6B0F12] focus-visible:ring-offset-1",
                active
                  ? "border-[#6B0F12] text-[#6B0F12]"
                  : "border-transparent text-stone-500 hover:text-stone-800 hover:border-stone-300",
              )}
            >
              <i className={cn("fas", f.icon, "text-[11px]")} aria-hidden />
              {f.label}
              {active && !loading && (
                <span className="ml-1 rounded-full bg-[#6B0F12]/10 px-1.5 text-[11px] font-bold tabular-nums">
                  {rows.length}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {loading ? (
        <Skeleton />
      ) : error ? (
        <EmptyState icon="fa-triangle-exclamation" title="Could not load the queue" message={error} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={FILTERS.find((f) => f.key === filter)!.icon}
          title={EMPTY_COPY[filter].title}
          message={EMPTY_COPY[filter].message}
        />
      ) : (
        <ul className="space-y-2">
          {rows.map((r) => (
            <li
              key={r.id}
              className="bg-white border border-stone-200 rounded-xl p-4 hover:border-stone-300 transition-colors"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Link
                      to={`/records/${r.id}`}
                      className="text-[14px] font-bold text-[#6B0F12] hover:underline"
                    >
                      {r.title}
                    </Link>
                    {r.resubmitted && (
                      <span
                        className="inline-flex items-center gap-1 rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[10px] font-bold text-indigo-700"
                        title={
                          r.resubmission_count === 1
                            ? "Resubmitted once after revisions"
                            : `Resubmitted ${r.resubmission_count} times after revisions`
                        }
                      >
                        <i className="fas fa-rotate text-[8px]" aria-hidden />
                        Resubmitted
                      </span>
                    )}
                  </div>

                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-stone-500">
                    {/* Server-worded: never map a stage key to English here. */}
                    <span className="font-semibold text-stone-700">{r.stage_label}</span>
                    <span aria-hidden>·</span>
                    <span>{r.record_type_name ?? "Unspecified type"}</span>
                    <span aria-hidden>·</span>
                    <span className={waitTone(r.waiting_days)}>
                      Waiting {waitLabel(r.waiting_days)}
                    </span>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-stone-400">
                      Other offices
                    </span>
                    <PeerClearanceStrip peers={r.peers} />
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <Link
                    to={`/review/${r.id}/evaluate`}
                    className="rounded-lg bg-[#6B0F12] px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-[#7d1215] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6B0F12] focus-visible:ring-offset-2"
                  >
                    {/* Naming the office is the point: at parallel_review this
                        records one office's clearance, not the record's
                        approval. */}
                    {r.your_office_label ? `Record ${r.your_office_label} clearance` : "Open decision"}
                  </Link>
                  {r.your_office_label && (
                    <span className="text-[10px] text-stone-400">
                      You are {r.your_office_label}
                    </span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
