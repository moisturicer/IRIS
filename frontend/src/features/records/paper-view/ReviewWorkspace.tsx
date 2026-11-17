import type { ReactNode } from "react";

import { Modal } from "@/components/ui/Modal";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

import { ReviewWorkspaceLayout } from "./ReviewWorkspaceLayout";

export interface ReviewWorkspaceProps {
  record: RecordDetail;
  /** What the capabilities adapter grants this viewer. */
  can: ReadonlySet<Capability>;
  /** The paper, as the Paper tab's reader; null when there is none to read. */
  reader: ReactNode;
  /** Bumped when the review changed, so the timeline re-reads the tracker. */
  timelineVersion: number;
  /** Something changed: re-read the record and the timeline. */
  onChanged: () => void;
  /**
   * Everything the Files section held, shown in the Documents drawer
   * (ADR-032 §10, 2026-11-04; IR-879). There is no Ask IRIS in Review (IR-372).
   */
  documents: ReactNode;
  /** Whether the drawer is open; kept in the URL as `?documents=open`. */
  documentsOpen: boolean;
  onDocuments: (open: boolean) => void;
  /**
   * The viewer owns the paper (IR-1206): the same workspace as reviewers,
   * with the author's tabs -- Readiness first, then Conversation, Threads and
   * Details -- and no tour and no Changes.
   */
  authorView?: boolean;
  /**
   * What left the owners' editorial header, shown at the top of their Details
   * (IR-1206): Edit details, the Proposal lineage and Continue as, each only
   * where the server offers it. Null when there is none.
   */
  authorDetails?: ReactNode;
  onOpenReview?: () => Promise<void>;
  /**
   * Show Version `n` in the reader, or the current paper for null (IR-873):
   * the Changes tab's *Show in paper* opens the Version a change is in.
   */
  onShowVersion?: (n: number | null) => void;
}

export function ReviewWorkspace(props: ReviewWorkspaceProps) {
  return (
    <>
      {/* One frame for authors and reviewers (IR-1206); the author's
          sticky action bar over the reader, and its bottom inset, are gone. */}
      <ReviewWorkspaceLayout {...props} />
      <DocumentsDrawer open={props.documentsOpen} onClose={() => props.onDocuments(false)}>
        {props.documents}
      </DocumentsDrawer>
    </>
  );
}

/**
 * All of a record's documents, in one dialog over Review (ADR-032 §10,
 * 2026-11-04; IR-879): the Files section as it was, moved, with the same
 * endpoints and checks. Full screen on a phone, a wide dialog above it.
 */
function DocumentsDrawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  return (
    <Modal open={open} onClose={onClose} title="All documents" size="lg" sheet>
      {children}
    </Modal>
  );
}
