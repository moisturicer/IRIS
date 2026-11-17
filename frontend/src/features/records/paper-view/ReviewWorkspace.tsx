import type { ReactNode } from "react";

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
   * The Documents tab's body (IR-1203): every document filed with the record.
   * It replaced the "All documents" drawer (IR-879). There is no Ask IRIS in
   * Review (IR-372).
   */
  documents: ReactNode;
  /**
   * The page was asked to show the documents -- `?documents=open`, or an old
   * `?section=files` link -- so the workspace opens its Documents tab, and
   * says so through `onDocumentsShown` so the page can drop the request.
   */
  showDocuments?: boolean;
  onDocumentsShown?: () => void;
  /**
   * The viewer owns the paper (IR-1206): the same workspace as reviewers,
   * with the author's tabs -- Readiness first, then Documents, Conversation,
   * Threads and Details -- and no tour and no Changes.
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

/** One frame for authors and reviewers (IR-1206); documents are its tab (IR-1203). */
export function ReviewWorkspace(props: ReviewWorkspaceProps) {
  return <ReviewWorkspaceLayout {...props} />;
}
