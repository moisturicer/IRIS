import type { ReactNode } from "react";

import type { Capability } from "@/features/records/capabilities";
import { PIPELINE_STATUS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";
import { CommentsSection } from "./CommentsSection";
import { SectionHeading } from "./headings";
import { IpTagger } from "./IpTagger";
import { NewVersionDialog } from "./NewVersionDialog";
import { PaperAiOverview } from "./PaperAiOverview";
import { RelatedPublishedResearch } from "./RelatedPublishedResearch";
import { RelatedWorks } from "./RelatedWorks";
import { ReviewOverview } from "./review-overview/ReviewOverview";
import type { ReviewTarget } from "./reviewTarget";

const OVERVIEW_STATUSES: ReadonlySet<string> = new Set([PIPELINE_STATUS.PUBLISHED, PIPELINE_STATUS.APPROVED, PIPELINE_STATUS.COMPLETED]);

interface OverviewSectionProps {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  userIsOwner: boolean;
  /** The signed-in viewer, for the comments they write. */
  viewerId: number | null;
  viewerName: string | null;
  /** View, Save, Cite and Share, under the abstract. */
  actions: ReactNode;
  /** *Submit new version* (IR-273): whether its dialog is open, and what the last one announced. */
  newVersionOpen: boolean;
  newVersionDone: string | null;
  onOpenNewVersion: () => void;
  onCloseNewVersion: () => void;
  onNewVersionDone: (outcome: string) => void;
  onNewVersionRefreshed: (fresh: RecordDetail) => void;
  /** The viewer is in this paper's review, and it is under way. */
  inReview: boolean;
  trackerVersion: number;
  onOpenReview: (target?: ReviewTarget) => void;
  /** In review, the record's details stand beside the abstract rather than beside the whole page. */
  details: ReactNode;
  /** A document or request changed. */
  onDocumentsChanged: () => Promise<void> | void;
  /** A save returned the Record. */
  onRecordReplaced: (updated: RecordDetail) => void;
}

/**
 * Paper View's Overview (IR-1271): while the paper is in review, where the
 * review stands and what the owner has been asked for (`ReviewOverview`);
 * then the abstract, the AI Overview, IP tagging, related research and the
 * published paper's comments. Related works wait until review is over.
 */
export function OverviewSection({
  record,
  can,
  userIsOwner,
  viewerId,
  viewerName,
  actions,
  newVersionOpen,
  newVersionDone,
  onOpenNewVersion,
  onCloseNewVersion,
  onNewVersionDone,
  onNewVersionRefreshed,
  inReview,
  trackerVersion,
  onOpenReview,
  details,
  onDocumentsChanged,
  onRecordReplaced,
}: OverviewSectionProps) {
  return (
    <>
      {/* In review: where it stands, who asks for what, and the owner's files. */}
      {inReview && (
        <ReviewOverview
          record={record}
          can={can}
          userIsOwner={userIsOwner}
          trackerVersion={trackerVersion}
          onOpenReview={onOpenReview}
          onSubmitNewVersion={onOpenNewVersion}
          onDocumentsChanged={onDocumentsChanged}
        />
      )}
      {/* Rendered while a version can be submitted, so the
          announcement lands when it fills; nowhere else, so the page
          keeps one status region (Share's) otherwise. */}
      {(record.revision.new_version != null || newVersionDone) && (
        <p role="status" aria-live="polite" className="sr-only">
          {newVersionDone ?? ""}
        </p>
      )}
      {newVersionOpen && record.revision.new_version && (
        <NewVersionDialog
          recordId={record.id}
          hint={record.revision.new_version}
          newManuscript={record.manuscript_unsubmitted}
          onClose={onCloseNewVersion}
          onDone={onNewVersionDone}
          onRefreshed={onNewVersionRefreshed}
        />
      )}

      {record.workflow_state === "rejected" && (
        <div className="rounded-card border border-stone-300 bg-surface p-4">
          <p className="text-sm font-bold text-brand-dark flex items-center gap-2">
            <i className="fas fa-circle-xmark text-xs" aria-hidden />
            This record was rejected
          </p>
          <p className="text-sm text-brand leading-relaxed mt-1">
            It cannot be resubmitted. Contact the relevant office if you have questions.
          </p>
        </div>
      )}

      {/* Reading sections are separated by space. */}
      <div className={cn(inReview && "grid items-start gap-8 overview-wide:grid-cols-[minmax(0,1fr)_clamp(17rem,25cqw,22rem)]")}>
      <div className="min-w-0 space-y-8">
      {/* The abstract shares the reading column with its heading and actions. */}
      <section>
        <SectionHeading>Abstract</SectionHeading>
        {record.abstract ? (
          <p className="text-justified text-lg text-stone-700 leading-7">
            {record.abstract}
          </p>
        ) : (
          <p className="text-sm text-stone-500 italic">
            No abstract was provided for this record.
          </p>
        )}
        <div className="mt-6 flex flex-wrap items-center gap-x-2 gap-y-2.5">
          {actions}
        </div>
      </section>

      {/* Only once the offices have decided: a draft, a paper in review or an archived one has no overview. */}
      {OVERVIEW_STATUSES.has(record.pipeline_status) && <PaperAiOverview record={record} />}

      {can.has("tag_ip") && (
        <IpTagger
          recordId={record.id}
          currentIpType={record.ip_type}
          onSaved={onRecordReplaced}
        />
      )}

      {/* The Novelty check (IR-312): the owner's own Proposal only,
          per ADR-029's 2026-09-26 amendment, item 9. */}
      {userIsOwner && record.record_type_name === "Proposal" && (
        <RelatedPublishedResearch recordId={record.id} />
      )}

      {record.pipeline_status !== PIPELINE_STATUS.IN_REVIEW && <RelatedWorks recordId={record.id} />}

      {/* Public comments belong to published papers' Overview only. */}
      {record.pipeline_status === "published" && (
        <CommentsSection recordId={record.id} viewerId={viewerId} viewerName={viewerName} />
      )}
      </div>
      {inReview && details}
      </div>
    </>
  );
}
