import type { ReactNode } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { ActionRequiredPanel } from "@/features/document-requests/ActionRequiredPanel";
import type { Capability } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";
import { WAITING_TARGET } from "../waitingOnYou";
import { CommentsSection } from "./CommentsSection";
import { SectionHeading } from "./headings";
import { IpTagger } from "./IpTagger";
import { PaperAiOverview } from "./PaperAiOverview";
import { RelatedPublishedResearch } from "./RelatedPublishedResearch";
import { RelatedWorks } from "./RelatedWorks";

interface OverviewSectionProps {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  userIsOwner: boolean;
  /** The signed-in viewer, for the comments they write. */
  viewerId: number | null;
  viewerName: string | null;
  /** View, Save, Cite and Share, under the abstract. */
  actions: ReactNode;
  /** Opens Review's Documents tab, where the owner uploads and submits (IR-1318). */
  onOpenDocuments: () => void;
  /** A save returned the Record. */
  onRecordReplaced: (updated: RecordDetail) => void;
}

/**
 * Paper View's Overview (IR-1271, moved out of the page unchanged): what is
 * waiting on the owner first, then the abstract, the AI Overview, IP
 * tagging, related research and the published paper's comments.
 */
export function OverviewSection({
  record,
  can,
  userIsOwner,
  viewerId,
  viewerName,
  actions,
  onOpenDocuments,
  onRecordReplaced,
}: OverviewSectionProps) {
  return (
    <>
      {/* Action required (spec §4.10): what is waiting on the
          owner comes first. The revision banner and the document
          requests below are that, whole; a separate "Your
          submission" summary repeated them and the rail (IR-1264). */}
      {/* Revision requests are answered through Submit new version, in Documents. */}
      {userIsOwner && record.revision.open.length > 0 && (
        <section
          id={WAITING_TARGET.revision}
          tabIndex={-1}
          aria-labelledby="revision-requested-heading"
          className="rounded-card border border-stone-300 bg-surface p-4 scroll-mt-20 focus:outline-none"
        >
          <h2
            id="revision-requested-heading"
            className="text-sm font-bold text-brand-dark flex items-center gap-2"
          >
            <i className="fas fa-arrow-rotate-left text-xs" aria-hidden />
            Revision requested
          </h2>
          <p className="text-sm text-brand leading-relaxed mt-1">
            Nothing can be decided on this record until you answer with a new version. Offices
            that already cleared it keep their clearance; only the reviewers who asked look again.
          </p>
          <ul className="mt-3 space-y-3">
            {record.revision.open.map((r) => (
              <li key={r.id} className="text-sm text-stone-900">
                <p className="font-semibold">
                  {r.label} asked for changes
                  {r.version != null && <span className="font-normal text-stone-600"> · on v{r.version}</span>}
                </p>
                {r.reason && (
                  <p className="text-justified mt-1 whitespace-pre-wrap break-words leading-relaxed text-stone-700">
                    {r.reason}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {/* Answered in the Documents tab, where the owner uploads and
              submits (IR-1318); here only why, and the way there. */}
          <div className="mt-4 border-t border-stone-300 pt-3">
            <p className="text-sm text-stone-700 leading-relaxed">
              Upload your changes and submit them in Documents.
            </p>
            <button type="button" onClick={onOpenDocuments} className={cn(PILL_PRIMARY, "mt-3", FOCUS_RING)}>
              <i className="fas fa-folder-open text-2xs" aria-hidden />
              Go to Documents
            </button>
          </div>
        </section>
      )}
      {userIsOwner && (
        <ActionRequiredPanel
          id={WAITING_TARGET.document}
          recordId={record.id}
          onOpenDocuments={onOpenDocuments}
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
      <div className="space-y-8">
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

      <PaperAiOverview record={record} />

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

      <RelatedWorks recordId={record.id} />

      {/* Public comments belong to published papers' Overview only. */}
      {record.pipeline_status === "published" && (
        <CommentsSection recordId={record.id} viewerId={viewerId} viewerName={viewerName} />
      )}
      </div>
    </>
  );
}
