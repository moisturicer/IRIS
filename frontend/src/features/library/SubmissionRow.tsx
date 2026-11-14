import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ClearanceStrip } from "@/components/shared/ClearanceStrip";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { ContinueProposal } from "@/features/records/ContinueProposal";
import { waitingHref } from "@/features/records/waitingOnYou";
import { DeleteDraft } from "./DeleteDraft";
import { waitingOn } from "./waitingOn";
import { cn, formatDate } from "@/lib/utils";
import type { MyResearchItem } from "@/types/records";

/**
 * A row's actions (IR-1084): one of Continue draft, the act that answers an
 * open request, or Open review. The Overview's short list (`brief`) shows
 * exactly one; the full list also offers Delete draft, quietly, on a draft.
 */
function RowActions({ item, brief, onDeleted }: { item: MyResearchItem; brief: boolean; onDeleted?: (id: number) => void }) {
  if (item.can_continue) return <ContinueProposal recordId={item.id} />;
  if (item.pipeline_status === "draft") {
    return (
      <>
        <Link to={`/?publish=${item.id}`} className={cn(PILL_PRIMARY, "min-h-9 px-4", FOCUS_RING)}>
          Continue draft <span className="sr-only">“{item.title}”</span>
        </Link>
        {!brief && onDeleted && <DeleteDraft recordId={item.id} title={item.title} onDeleted={onDeleted} />}
      </>
    );
  }
  // One link per open request, straight to the act on Paper View (IR-625).
  const waiting = brief ? item.submitter_status.waiting_on_you.slice(0, 1) : item.submitter_status.waiting_on_you;
  if (waiting.length === 0) {
    return (
      <Link to={`/records/${item.id}`} className={cn(PILL_SECONDARY, "min-h-9 px-4", FOCUS_RING)}>
        Open review <span className="sr-only">of “{item.title}”</span>
      </Link>
    );
  }
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
  /** The Overview's short list: no clearance strip, one action, no Delete. */
  brief?: boolean;
  /** Offered on a draft: the row is gone once the server deleted it. */
  onDeleted?: (id: number) => void;
}

/**
 * One of the owner's records as a row in a ruled list (IR-410). The title is
 * the row's one link, stretched over the row; only the actions sit above it.
 * The status words are the server's (`submitter_status.line`); the sentence
 * under the title says what the record waits on (`waitingOn`, IR-1084).
 */
export function SubmissionRow({ item, brief = false, onDeleted }: SubmissionRowProps) {
  const people = [
    item.authors.map((author) => author.name).join(", "),
    item.adviser_name && `Adviser: ${item.adviser_name}`,
  ].filter(Boolean).join(" · ");
  const actions = <RowActions item={item} brief={brief} onDeleted={onDeleted} />;

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
            <p className="mt-1 text-small text-stone-800">{waitingOn(item)}</p>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 md:flex-col md:items-end">
            <StatusBadge state={item.workflow_state} label={item.submitter_status.line} />
            <span className="text-label tabular-nums text-stone-500">Updated {formatDate(item.updated_at)}</span>
          </div>
        </div>

        {!brief && <ClearanceStrip entries={item.clearance_strip} className="mt-2" />}
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
        tone === "waiting" ? "divide-stone-200 border-stone-300" : "divide-stone-100 border-stone-200",
      )}
    >
      {children}
    </ul>
  );
}
