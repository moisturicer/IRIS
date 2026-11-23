import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ClearanceStrip } from "@/components/shared/ClearanceStrip";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { RowMenu, type RowMenuItem } from "@/features/accounts/RowMenu";
import { ContinueProposal } from "@/features/records/ContinueProposal";
import { usePublishHref } from "@/features/publish/publishLink";
import { cn, formatDate } from "@/lib/utils";
import type { MyResearchItem } from "@/types/records";

import { DeleteDraftDialog } from "./DeleteDraft";

/**
 * Where the row itself leads: a draft opens Publish over this page, since a
 * draft has no paper page (IR-1227) and going through one would leave My
 * Library (IR-1258); anything else opens Paper View. The whole row is that
 * link (IR-1261), so it carries no "Continue draft" or "Open review" button.
 */
function rowHref(item: MyResearchItem, publishHref: (target: number) => string) {
  return item.pipeline_status === "draft" ? publishHref(item.id) : `/records/${item.id}`;
}

interface SubmissionRowProps {
  item: MyResearchItem;
  /** Offered on a draft: the row is gone once the server deleted it. */
  onDeleted?: (id: number) => void;
}

/**
 * One of the owner's records as a row in a ruled list (IR-410). The title is
 * the row's link, stretched over the row (`rowHref`). The status words are the
 * server's (`submitter_status.line`). One action at most: Continue on an accepted Proposal. Open requests are
 * answered on the paper's Overview, so the row carries no button for them;
 * Delete draft is in its menu (IR-1311).
 */
export function SubmissionRow({ item, onDeleted }: SubmissionRowProps) {
  const publishHref = usePublishHref();
  const [deleting, setDeleting] = useState(false);
  // Open requests are answered on the paper's Overview, which the row opens;
  // the row offers only what is not there: Continue on a Proposal, Delete on a draft.
  const menu: RowMenuItem[] = item.pipeline_status === "draft" && onDeleted
    ? [{ key: "delete", label: "Delete draft", danger: true, onSelect: () => setDeleting(true) }]
    : [];
  const action: ReactNode = item.can_continue ? <ContinueProposal recordId={item.id} /> : null;

  return (
    <li className={cn("group relative px-4 py-3 hover:bg-stone-50 sm:px-5", COLOUR_TRANSITION)}>
      <div className="flex items-center gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-x-6 gap-y-2 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-stone-600">
              <span className="font-medium">{item.record_type_name ?? "Research"}</span>
              {item.adviser_name && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-stone-100 py-0.5 pl-1.5 pr-2.5 font-medium text-stone-700">
                  <i aria-hidden className="fas fa-user-tie text-3xs text-stone-500" />
                  <span className="sr-only">Adviser: </span>{item.adviser_name}
                </span>
              )}
              <span className="tabular-nums">Updated {formatDate(item.updated_at)}</span>
            </p>
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
            <ClearanceStrip entries={item.clearance_strip} className="mt-1.5" />
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 md:justify-end">
            <StatusBadge state={item.workflow_state} label={item.submitter_status.line} />
            {/* Above the row's link, as the menu is. */}
            {action && <div className="relative z-10">{action}</div>}
          </div>
        </div>

        {/* Above the row's link, so a press opens the menu rather than the record. */}
        {menu.length > 0 && (
          <div className="relative z-10 -mr-2 shrink-0">
            <RowMenu small vertical label={`Actions for ${item.title}`} items={menu} />
          </div>
        )}
      </div>

      {onDeleted && item.pipeline_status === "draft" && (
        <DeleteDraftDialog
          recordId={item.id}
          title={item.title}
          open={deleting}
          onClose={() => setDeleting(false)}
          onDeleted={onDeleted}
        />
      )}
    </li>
  );
}

/** A ruled panel of rows. */
export function SubmissionPanel({ children }: { children: ReactNode }) {
  return (
    <ul className="divide-y divide-stone-100 overflow-hidden rounded-card border border-stone-200 bg-white">
      {children}
    </ul>
  );
}
