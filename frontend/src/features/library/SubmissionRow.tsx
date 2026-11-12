import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { StatusBadge } from "@/components/shared/StatusBadge";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { ContinueProposal } from "@/features/records/ContinueProposal";
import { waitingHref } from "@/features/records/waitingOnYou";
import { DeleteDraft } from "./DeleteDraft";
import { cn, formatDate } from "@/lib/utils";
import type { MyResearchItem } from "@/types/records";

/**
 * Who has the record now and which offices have cleared it, as one quiet
 * line. A clearance kept through a resubmission says so: that is
 * clearance-aware resubmission (ADR-003), shown where the owner works. Only
 * parties the server named appear; an office that was never routed the record
 * is not drawn as a pending step.
 */
function ReviewTrack({ item }: { item: MyResearchItem }) {
  const cleared = new Set<string>(item.cleared_offices.map((o) => o.office));
  const holding = item.holders.filter((h) => !cleared.has(h.party));
  if (holding.length === 0 && item.cleared_offices.length === 0) return null;

  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-label">
      {holding.map((holder) => (
        <span key={holder.party} className="inline-flex items-center gap-1.5 font-semibold text-brand">
          <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden />
          {holder.label} reviewing
        </span>
      ))}
      {item.cleared_offices.map((office) => (
        <span key={office.office} className="inline-flex items-center gap-1.5 font-semibold text-stone-800">
          <i className="fas fa-check text-3xs" aria-hidden />
          {office.label} cleared{office.preserved && <span className="font-normal text-stone-600"> · kept</span>}
        </span>
      ))}
    </p>
  );
}

function RowActions({ item, onDeleted }: { item: MyResearchItem; onDeleted?: (id: number) => void }) {
  if (item.can_continue) return <ContinueProposal recordId={item.id} />;
  if (item.pipeline_status === "draft") {
    return (
      <>
        <Link to={`/?publish=${item.id}`} className={cn(PILL_SECONDARY, "min-h-9 px-4", FOCUS_RING)}>Continue</Link>
        {onDeleted && <DeleteDraft recordId={item.id} title={item.title} onDeleted={onDeleted} />}
      </>
    );
  }
  // One link per open request, straight to the act on Paper View (IR-625).
  const waiting = item.submitter_status.waiting_on_you;
  if (waiting.length === 0) return null;
  return (
    <>
      {waiting.map((request, i) => (
        <Link
          key={`${request.kind}-${request.party}`}
          to={waitingHref(item.id, request)}
          className={cn(i === 0 ? PILL_PRIMARY : PILL_SECONDARY, "min-h-9 px-4", FOCUS_RING)}
        >
          {request.action_label}{" "}
          <span className="sr-only">({request.label})</span>
        </Link>
      ))}
    </>
  );
}

interface SubmissionRowProps {
  item: MyResearchItem;
  /** The Overview's short list: no review track and no actions. */
  brief?: boolean;
  /** Offered on a draft: the row is gone once the server deleted it. */
  onDeleted?: (id: number) => void;
}

/**
 * One of the owner's records as a row in a ruled list (IR-410). The title is
 * the row's one link, stretched over the row; only the actions sit above it.
 * The status words are the server's (`submitter_status.line`).
 */
export function SubmissionRow({ item, brief = false, onDeleted }: SubmissionRowProps) {
  const people = [
    item.authors.map((author) => author.name).join(", "),
    item.adviser_name && `Adviser: ${item.adviser_name}`,
  ].filter(Boolean).join(" · ");
  const actions = brief ? null : <RowActions item={item} onDeleted={onDeleted} />;

  return (
    <li className={cn("group relative flex gap-4 px-4 py-4 hover:bg-stone-50 sm:px-5", COLOUR_TRANSITION)}>
      <span
        className="mt-0.5 hidden h-10 w-10 shrink-0 place-items-center rounded-lg bg-stone-100 text-stone-500 sm:grid"
        aria-hidden
      >
        <i className="fas fa-file-lines text-small" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-col gap-x-6 gap-y-2 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <p className="text-label text-stone-600">{item.record_type_name ?? "Research"}</p>
            <h3 className="mt-0.5 font-display text-title font-semibold leading-snug text-stone-900">
              <Link
                to={`/records/${item.id}`}
                className={cn(
                  "rounded-sm group-hover:text-brand",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                  "after:absolute after:inset-0 after:content-['']",
                )}
              >
                {item.title}
              </Link>
            </h3>
            {people && <p className="mt-0.5 truncate text-small text-stone-600">{people}</p>}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 md:flex-col md:items-end">
            <StatusBadge state={item.workflow_state} label={item.submitter_status.line} />
            <span className="text-label tabular-nums text-stone-500">Updated {formatDate(item.updated_at)}</span>
          </div>
        </div>

        {!brief && <ReviewTrack item={item} />}
        {actions && <div className="relative z-10 mt-3 flex flex-wrap items-center gap-2">{actions}</div>}
      </div>

      <i
        className="fas fa-chevron-right mt-4 hidden text-label text-stone-400 group-hover:text-brand md:block"
        aria-hidden
      />
    </li>
  );
}

/** A ruled panel of rows. */
export function SubmissionPanel({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "waiting" }) {
  return (
    <ul
      className={cn(
        "divide-y overflow-hidden rounded-2xl border bg-white",
        tone === "waiting" ? "divide-brand-100 border-brand-200" : "divide-stone-100 border-stone-200",
      )}
    >
      {children}
    </ul>
  );
}
