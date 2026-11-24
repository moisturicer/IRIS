import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ClearanceStrip } from "@/components/shared/ClearanceStrip";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { ContinueProposal } from "@/features/records/ContinueProposal";
import { waitingHref } from "@/features/records/waitingOnYou";
import { usePublishHref } from "@/features/publish/publishLink";
import { DeleteRecord, type DeleteKind } from "./DeleteRecord";
import { cn, formatDate } from "@/lib/utils";
import type { MyResearchItem } from "@/types/records";

/**
 * Where the row itself leads: a draft opens Publish over this page, since a
 * draft has no paper page (IR-1227) and going through one would leave My
 * Library (IR-1258); anything else opens Paper View. The whole row is that
 * link (IR-1261), so it carries no "Continue draft" or "Open review" button.
 */
function rowHref(item: MyResearchItem, publishHref: (target: number) => string) {
  return item.pipeline_status === "draft" ? publishHref(item.id) : `/records/${item.id}`;
}

/**
 * The acts a row offers beyond opening it (IR-1084): continuing a finished
 * proposal, or the act that answers each open request. The Overview's short
 * list (`brief`) shows only the first request. Null when there is none.
 */
function rowActions(item: MyResearchItem, brief: boolean): ReactNode {
  if (item.can_continue) return <ContinueProposal recordId={item.id} />;
  if (item.pipeline_status === "draft") return null;
  // One link per open request, straight to the act on Paper View (IR-625).
  const waiting = brief ? item.submitter_status.waiting_on_you.slice(0, 1) : item.submitter_status.waiting_on_you;
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

/**
 * Which trash can a row carries, if any: a draft's, or withdrawing a paper in
 * review, which the server names `withdraw_submission` (IR-1282). Accepted
 * work (`request_deletion`, a request RDCO decides) and rejected records get
 * none here.
 */
function deleteKindOf(item: MyResearchItem): DeleteKind | null {
  if (item.pipeline_status === "draft") return "draft";
  if (item.delete_act === "withdraw_submission") return "withdraw";
  return null;
}

interface SubmissionRowProps {
  item: MyResearchItem;
  /** The Overview's short list: no clearance strip, one action (and a draft's Delete). */
  brief?: boolean;
  /** Offered on a draft or a paper in review: the row is gone once the server deleted it. */
  onDeleted?: (id: number) => void;
}

/**
 * One of the owner's records as a row in a ruled list (IR-410). The title is
 * the row's one link, stretched over the row, so a click anywhere opens it
 * (`rowHref`); only the actions and a draft's trash can sit above it. The
 * status words are the server's (`submitter_status.line`). IR-1306 dropped the
 * sentence under the title: the status, the clearance strip and the action say it.
 */
export function SubmissionRow({ item, brief = false, onDeleted }: SubmissionRowProps) {
  const publishHref = usePublishHref();
  const authors = item.authors.map((author) => author.name).join(", ");
  const actions = rowActions(item, brief);
  const deleteKind = onDeleted ? deleteKindOf(item) : null;

  return (
    <li className={cn("group relative flex gap-4 px-4 py-4 hover:bg-stone-50 sm:px-5", COLOUR_TRANSITION)}>
      <span
        className="mt-0.5 hidden h-10 w-10 shrink-0 place-items-center rounded-control bg-stone-100 text-stone-600 sm:grid"
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
                to={rowHref(item, publishHref)}
                className={cn(
                  "rounded-control group-hover:text-brand",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                  "after:absolute after:inset-0 after:content-['']",
                )}
              >
                {item.title}
              </Link>
            </h3>
            {/* Who, without a sentence about it (IR-1306): authors, then the Adviser marked by an icon. */}
            {(authors || item.adviser_name) && <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 break-words text-small text-stone-600">
              {authors && <span>{authors}</span>}
              {item.adviser_name && <span className="inline-flex items-center gap-1.5">
                <i aria-hidden className="fas fa-user-tie text-label text-stone-400" />
                <span className="sr-only">Adviser: </span>{item.adviser_name}
              </span>}
            </p>}
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 md:flex-col md:items-end">
            <StatusBadge state={item.workflow_state} label={item.submitter_status.line} />
            <span className="text-label tabular-nums text-stone-500">Updated {formatDate(item.updated_at)}</span>
            {/* The trash can alone, rightmost under the date and level with the
                people line (IR-1279); the row itself continues the draft. Above
                the row's link, so a press deletes rather than opens. The
                negative margin lines its icon up with the date's right edge. */}
            {deleteKind && onDeleted && (
              <div className="relative z-10 -mr-2 ml-auto md:ml-0">
                <DeleteRecord kind={deleteKind} recordId={item.id} title={item.title} onDeleted={onDeleted} />
              </div>
            )}
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
        "divide-y overflow-hidden rounded-card border bg-white",
        tone === "waiting" ? "divide-stone-200 border-stone-300" : "divide-stone-100 border-stone-200",
      )}
    >
      {children}
    </ul>
  );
}
