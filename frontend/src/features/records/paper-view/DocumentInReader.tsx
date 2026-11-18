import { Suspense, useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui";
import { Skeleton } from "@/components/ui/Skeleton";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn, downloadBlob } from "@/lib/utils";
import { CONTROL_SIZE } from "./controls";
import { ImageReader } from "./ImageReader";
import { PaperPdfReader } from "./lazyReader";
import { DOCUMENT_ROUTES, readerDocumentKey, readerFormat, type ReaderDocument } from "./readerDocument";

/**
 * The document shown, the address it was opened at (a change of view brings
 * the manuscript back), and the control that opened it, for focus to return to.
 */
export interface ShownDocumentState {
  document: ReaderDocument;
  at: string;
  opener: HTMLElement | null;
}

const NO_REGIONS: never[] = [];
const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/** A control focus can go back to: still on the page, and not behind a closed or inert pane. */
const reachable = (el: HTMLElement | null): el is HTMLElement =>
  el !== null && el.isConnected && el.closest('[inert],[aria-hidden="true"],[hidden]') === null;

/**
 * A supporting document in Review's reader (IR-1203): named above the reader,
 * with the way back to the manuscript. The reader keeps find, zoom and pages,
 * and its download saves this document. Nothing is offered on a selection:
 * highlights, Ask IRIS and review threads belong to the manuscript.
 *
 * Opening moves focus to the strip, so a keyboard or screen-reader user is
 * told what the reader now shows. Back puts it on the control that opened
 * the document, or, when that is gone (a narrow pane closed over it), on the
 * first control of the manuscript's reader.
 */
export function DocumentInReader({
  recordId,
  shown,
  onBack,
  fill,
  contained,
}: {
  recordId: number;
  shown: ShownDocumentState;
  onBack: () => void;
  fill: boolean;
  contained: boolean;
}) {
  const { document: doc, opener } = shown;
  const descriptionId = useId();
  const strip = useRef<HTMLDivElement>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    strip.current?.focus();
  }, [doc.kind, doc.id]);

  const back = () => {
    const area = strip.current?.parentElement ?? null;
    onBack();
    requestAnimationFrame(() => {
      if (reachable(opener)) opener.focus();
      else area?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    });
  };
  const save = () => {
    setSaving(true);
    setFailed(false);
    DOCUMENT_ROUTES[doc.kind].download(doc.id)
      .then(({ data }) => downloadBlob(data, doc.fileName))
      .catch(() => setFailed(true))
      .finally(() => setSaving(false));
  };
  // The manuscript's control, as the reader's toolbar draws it (PaperDownloadControl).
  const downloadControl = (
    <Button
      variant="ghost"
      size={fill ? "sm" : "icon"}
      onClick={save}
      loading={saving}
      aria-label={`Download ${doc.label}`}
      className={cn(fill && "text-stone-600", fill && CONTROL_SIZE)}
    >
      <i className="fas fa-download" aria-hidden />
      {fill && <span aria-hidden className="hidden reading-split:inline">Download</span>}
    </Button>
  );

  return (
    <>
      <div
        ref={strip}
        role="group"
        aria-label="Shown in the reader"
        aria-describedby={descriptionId}
        tabIndex={-1}
        // Stone, like the bars around the page: only the paper is white (DESIGN.md).
        className={cn(
          "mb-3 flex flex-wrap items-center justify-between gap-2 rounded-card border border-stone-200 bg-stone-100 px-4 py-2",
          FOCUS_RING,
        )}
      >
        <p id={descriptionId} className="min-w-0 break-words text-small text-stone-700">
          <span className="font-semibold text-stone-900">{doc.label}</span>
          {" · a supporting document, not the manuscript"}
        </p>
        <button type="button" onClick={back} className={cn(PILL_SECONDARY, FOCUS_RING, CONTROL_SIZE, "px-3")}>
          <i className="fas fa-arrow-left text-2xs" aria-hidden />
          Back to the manuscript
        </button>
      </div>
      <p role="status" className="text-small font-semibold text-brand empty:hidden">
        {failed ? `Could not download ${doc.fileName}. Please try again.` : ""}
      </p>
      {readerFormat(doc.fileName) === "image" ? (
        <ImageReader document={doc} downloadControl={downloadControl} />
      ) : (
        <Suspense fallback={<Skeleton rows={8} label="Loading the reader…" />}>
          <PaperPdfReader
            recordId={recordId}
            document={doc}
            scrollToPage={null}
            highlightRegions={NO_REGIONS}
            navKey={`document-${readerDocumentKey(doc)}`}
            contained={contained}
            fill={fill}
            downloadControl={downloadControl}
          />
        </Suspense>
      )}
    </>
  );
}
