import { useEffect, useRef, type ReactNode } from "react";

import { Modal } from "@/components/ui/Modal";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { useElementHeight } from "@/hooks/useElementHeight";
import type { Capability } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import { READING_PANE_HEIGHT, READING_PANE_TOP } from "./paneLayout";
import { ReviewActionBar } from "./ReviewActionBar";
import { ReviewTimeline } from "./ReviewTimeline";
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
  /** Authors retain their existing timeline and reader. */
  authorView?: boolean;
  onOpenReview?: () => Promise<void>;
  /**
   * The author's action bar's height in px, as it changes, and 0 once the
   * tab closes (IR-477). Below `reading-wide` the bar sticks over the bottom
   * of the screen, so the page hands this to the reader as `bottomInset`.
   */
  onBarInset?: (px: number) => void;
}

export function ReviewWorkspace(props: ReviewWorkspaceProps) {
  return (
    <>
      {props.authorView ? <AuthorReviewWorkspace {...props} /> : <ReviewWorkspaceLayout {...props} />}
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
    <Modal open={open} onClose={onClose} title="All documents" size="max-w-3xl" sheet>
      {children}
    </Modal>
  );
}

/**
 * Review mode's composition boundary (IR-680). The page owns the record,
 * section selection and reader; this component receives the viewer's
 * capabilities and existing callbacks, and adds no data requests.
 * ReviewTimeline retains its existing tracker read and status strip.
 *
 * The Review section (IR-412; spec §4.6, §4.7): the paper on the left and,
 * on the right, the review pane -- the timeline, with the action bar under
 * it. Like a pull request: the work, what has happened to it, and what you
 * may do next.
 *
 * In a `reading-wide` workspace (IR-569) the pane is a sticky column the
 * reader's height, beside the reader and never over it, sharing the Paper
 * tab's pane geometry (IR-352). Narrower, the paper stacks above the pane, and the action bar sticks to the
 * bottom of the screen the whole way down, paper included.
 *
 * **No Ask IRIS here** (spec §4.6, decided 2026-09-26; kept by IR-879): a
 * participant opens Ask IRIS on Overview or at `/ai`, for example in a new
 * tab. *Documents* opens the drawer that replaced the Files section.
 *
 * The bar's measured height goes to `onBarInset`, so the reader lands a
 * citation above the bar rather than under it (IR-477; spec Appendix K,
 * amended). Wide, the bar sits in the pane beside the reader, and the
 * contained reader ignores the inset.
 *
 * Decisions use the adviser-first review actions in `REVIEW_ACTIONS`.
 */
function AuthorReviewWorkspace({
  record,
  can,
  reader,
  timelineVersion,
  onChanged,
  onDocuments,
  onBarInset,
}: ReviewWorkspaceProps) {
  const [measureBar, barHeight] = useElementHeight<HTMLDivElement>();
  const reportRef = useRef(onBarInset);
  reportRef.current = onBarInset;
  useEffect(() => {
    reportRef.current?.(barHeight);
  }, [barHeight]);
  useEffect(() => () => reportRef.current?.(0), []);

  return (
    <div className={cn("reading-wide:flex reading-wide:gap-6 reading-wide:items-start", !reader && "max-w-3xl mx-auto")}>
      {reader && <div className="min-w-0 reading-wide:flex-1">{reader}</div>}

      {/* The pane and its bar. One column when wide; narrower this box is
          `contents`, so the bar's sticky range is the whole section, paper
          and all, rather than the pane alone. */}
      <div
        className={cn(
          "contents reading-wide:flex reading-wide:flex-col reading-wide:shrink-0 reading-wide:overflow-hidden",
          "reading-wide:rounded-2xl reading-wide:bg-white reading-wide:ring-1 reading-wide:ring-stone-200",
          reader
            ? cn("reading-wide:sticky reading-wide:w-[26rem]", READING_PANE_TOP, READING_PANE_HEIGHT)
            : "reading-wide:w-full",
        )}
      >
        <div
          className={cn(
            "mt-6 rounded-2xl bg-white ring-1 ring-stone-200 p-card space-y-4",
            "reading-wide:mt-0 reading-wide:rounded-none reading-wide:ring-0 reading-wide:flex-1",
            "reading-wide:min-h-0 reading-wide:overflow-y-auto",
          )}
        >
          <button
            type="button"
            onClick={() => onDocuments(true)}
            className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-11 px-4")}
          >
            <i className="fas fa-folder-open text-xs" aria-hidden />
            Documents
          </button>
          <ReviewTimeline key={timelineVersion} recordId={record.id} canComment={can.has("comment_review")} />
        </div>

        <ReviewActionBar
          record={record}
          can={can}
          onChanged={onChanged}
          boxRef={measureBar}
          className={cn(
            "sticky bottom-0 z-20 mt-4 rounded-t-2xl bg-white ring-1 ring-stone-200 shadow-card-md px-3 py-2",
            "reading-wide:static reading-wide:z-auto reading-wide:mt-0 reading-wide:rounded-none",
            "reading-wide:ring-0 reading-wide:shadow-none reading-wide:border-t reading-wide:border-stone-200",
            "reading-wide:px-5 reading-wide:py-3",
          )}
        />
      </div>
    </div>
  );
}
