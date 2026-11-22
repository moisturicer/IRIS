import type { ReactNode } from "react";

import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { ActionRequiredPanel } from "@/features/document-requests/ActionRequiredPanel";
import type { Capability } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";
import { WAITING_TARGET } from "../waitingOnYou";
import { CommentsSection } from "./CommentsSection";
import { SectionHeading } from "./headings";
import { IpTagger } from "./IpTagger";
import { NewVersionDialog, newVersionSummary } from "./NewVersionDialog";
import { PaperAiOverview } from "./PaperAiOverview";
import { RelatedPublishedResearch } from "./RelatedPublishedResearch";
import { RelatedWorks } from "./RelatedWorks";
import { RevisionManuscriptUpload } from "./RevisionManuscriptUpload";

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
  /** A document or request changed. */
  onDocumentsChanged: () => Promise<void> | void;
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
  newVersionOpen,
  newVersionDone,
  onOpenNewVersion,
  onCloseNewVersion,
  onNewVersionDone,
  onNewVersionRefreshed,
  onDocumentsChanged,
  onRecordReplaced,
}: OverviewSectionProps) {
  return (
    <>
      {/* Action required (spec §4.10): what is waiting on the
          owner comes first. The revision banner and the document
          requests below are that, whole; a separate "Your
          submission" summary repeated them and the rail (IR-1264). */}
      {/* Revision requests are answered through Submit new version. */}
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
          {can.has("create_version") && record.revision.new_version && (
            <div className="mt-4 border-t border-stone-300 pt-3">
              <p className="text-sm text-stone-700 leading-relaxed">
                Upload your revised manuscript here, add any requested document below, or edit
                the details, then submit. {newVersionSummary(record.revision.new_version)}
              </p>
              {can.has("replace_manuscript") && (
                <div className="mt-3">
                  <RevisionManuscriptUpload
                    recordId={record.id}
                    staged={record.manuscript_unsubmitted}
                    onUploaded={onDocumentsChanged}
                  />
                </div>
              )}
              {record.revision.new_version.blocked && (
                <p id="new-version-blocked" className="text-sm text-brand mt-2">
                  {record.revision.new_version.blocked}
                </p>
              )}
              <button
                type="button"
                onClick={onOpenNewVersion}
                aria-describedby={record.revision.new_version.blocked ? "new-version-blocked" : undefined}
                className={cn(PILL_PRIMARY, "mt-3")}
              >
                <i className="fas fa-paper-plane text-2xs" aria-hidden />
                Submit new version
              </button>
            </div>
          )}
        </section>
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

      {userIsOwner && (
        <ActionRequiredPanel
          id={WAITING_TARGET.document}
          recordId={record.id}
          onChanged={onDocumentsChanged}
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
