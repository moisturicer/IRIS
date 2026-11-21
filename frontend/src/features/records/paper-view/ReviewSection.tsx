import type { ReactNode } from "react";

import { hasPaper, type Capability } from "@/features/records/capabilities";
import type { RecordDetail, ThreadDocument } from "@/types/records";
import { DocumentInReader, type ShownDocumentState } from "./DocumentInReader";
import { DocumentsTab } from "./DocumentsTab";
import type { ReaderDocument } from "./readerDocument";
import { ReviewWorkspaceLayout } from "./ReviewWorkspaceLayout";

interface ReviewSectionProps {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  userIsOwner: boolean;
  reviewing: boolean;
  /** Edit details, lineage and Continue as, on the owner's Details tab (IR-1206). */
  authorDetails: ReactNode;
  onOpenReview: () => Promise<void>;
  onShowVersion: (n: number | null) => void;
  /** The manuscript's reader (PaperSection). */
  reader: ReactNode;
  /** The supporting document shown instead of the manuscript, if any (IR-1203). */
  shown: ShownDocumentState | null;
  onShowManuscript: () => void;
  onShowThreadDocument: (thread: ThreadDocument) => void;
  onOpenDocument: (document: ReaderDocument, opener: HTMLElement) => void;
  timelineVersion: number;
  onChanged: () => Promise<void>;
  /** Review's Documents tab is asked for by the address. */
  showDocuments: boolean;
  onDocumentsShown: () => void;
}

/**
 * Paper View's Review (IR-1271, moved out of the page unchanged): one
 * full-height workspace for everyone in the review (IR-1206), its reader
 * showing the manuscript or a supporting document, and its Documents tab.
 * No Ask IRIS in Review (ADR-032 §10, IR-372 as kept by IR-879).
 */
export function ReviewSection({
  record,
  can,
  userIsOwner,
  reviewing,
  authorDetails,
  onOpenReview,
  onShowVersion,
  reader,
  shown,
  onShowManuscript,
  onShowThreadDocument,
  onOpenDocument,
  timelineVersion,
  onChanged,
  showDocuments,
  onDocumentsShown,
}: ReviewSectionProps) {
  const paper = hasPaper(record);
  return (
    <ReviewWorkspaceLayout
      record={record}
      authorView={userIsOwner}
      authorDetails={userIsOwner ? authorDetails : undefined}
      onOpenReview={onOpenReview}
      onShowVersion={onShowVersion}
      can={can}
      reader={paper
        ? shown
          // Review is always a full-height workspace, so its reader fills it.
          ? <DocumentInReader recordId={record.id} shown={shown} onBack={onShowManuscript} fill contained />
          : reader
        : null}
      onShowManuscript={onShowManuscript}
      onShowDocument={paper ? onShowThreadDocument : undefined}
      timelineVersion={timelineVersion}
      onChanged={onChanged}
      showDocuments={showDocuments}
      // Once shown, the request is spent: the tab is the reviewer's to change.
      onDocumentsShown={onDocumentsShown}
      documents={
        <DocumentsTab
          record={record}
          owner={userIsOwner}
          editable={can.has("edit_details")}
          reviewing={reviewing}
          attach={can.has("attach_file")}
          replaceManuscript={can.has("replace_manuscript")}
          onChanged={onChanged}
          onOpen={paper ? onOpenDocument : undefined}
        />
      }
    />
  );
}
