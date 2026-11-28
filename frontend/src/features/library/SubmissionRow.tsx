import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ClearanceStrip } from "@/components/shared/ClearanceStrip";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { reviewHref } from "@/features/records/capabilities";
import { ContinueProposal } from "@/features/records/ContinueProposal";
import { waitingHref } from "@/features/records/waitingOnYou";
import { usePublishHref } from "@/features/publish/publishLink";
import { DeleteRecord, type DeleteKind } from "./DeleteRecord";
import { PIPELINE_STATUS } from "@/lib/constants";
import { cn, formatDate } from "@/lib/utils";
import type { MyResearchItem } from "@/types/records";

/**
 * Where the row itself leads: a draft opens Publish over this page, since a
 * draft has no paper page (IR-1227) and going through one would leave My
 * Library (IR-1258). A paper waiting on its author opens where the request is
 * answered (IR-1321), so the row carries no per-request button. A published
 * paper opens its review, which a plain link to it no longer shows its author
 * (IR-1339); anything else opens Paper View. The whole row is that link
 * (IR-1261).
 */
function rowHref(item: MyResearchItem, publishHref: (target: number) => string) {
  if (item.pipeline_status === "draft") return publishHref(item.id);
  const [request] = item.submitter_status.waiting_on_you;
  if (request) return waitingHref(item.id, request);
  return item.pipeline_status === PIPELINE_STATUS.PUBLISHED ? reviewHref(item.id) : `/records/${item.id}`;
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
  /** The Overview's short list: no clearance strip. */
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
        {item.can_continue && <div className="relative z-10 mt-3 flex flex-wrap items-center gap-2"><ContinueProposal recordId={item.id} /></div>}
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
