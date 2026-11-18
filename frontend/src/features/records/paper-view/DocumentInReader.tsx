import { lazy, Suspense, useState } from "react";
import { documentsApi } from "@/api/documents";
import { Skeleton } from "@/components/ui/Skeleton";
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn, downloadBlob } from "@/lib/utils";
import { CONTROL_SIZE } from "./controls";
import type { ReaderDocument } from "./readerDocument";

const PaperPdfReader = lazy(() => import("./PaperPdfReader").then((m) => ({ default: m.PaperPdfReader })));

/** The document shown, and the address it was opened at: a change of view brings the manuscript back. */
export interface ShownDocumentState {
  document: ReaderDocument;
  at: string;
}

const NO_REGIONS: never[] = [];

/**
 * A supporting document in Review's reader (IR-1203): named above the reader,
 * with the way back to the manuscript. The reader keeps find, zoom and pages,
 * and its download saves this document. Nothing is offered on a selection:
 * highlights, Ask IRIS and review threads belong to the manuscript.
 */
export function DocumentInReader({
  recordId,
  document,
  onBack,
  fill,
  contained,
}: {
  recordId: number;
  document: ReaderDocument;
  onBack: () => void;
  fill: boolean;
  contained: boolean;
}) {
  const [failed, setFailed] = useState(false);
  const save = () => {
    setFailed(false);
    const fetch = document.kind === "upload" ? documentsApi.downloadUpload : documentsApi.downloadFile;
    fetch(document.id)
      .then(({ data }) => downloadBlob(data as Blob, document.fileName))
      .catch(() => setFailed(true));
  };
  return (
    <>
      <div
        role="group"
        aria-label="Shown in the reader"
        className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-card border border-stone-300 bg-surface px-4 py-2"
      >
        <p className="min-w-0 break-words text-small text-stone-700">
          <span className="font-semibold text-stone-900">{document.label}</span>
          {" · a supporting document, not the manuscript"}
        </p>
        <button type="button" onClick={onBack} className={cn(PILL_SECONDARY, FOCUS_RING, CONTROL_SIZE, "px-3")}>
          <i className="fas fa-arrow-left text-2xs" aria-hidden />
          Back to the manuscript
        </button>
      </div>
      <p role="status" className="text-small font-semibold text-brand empty:hidden">
        {failed ? `Could not download ${document.fileName}. Please try again.` : ""}
      </p>
      <Suspense fallback={<Skeleton rows={8} label="Loading the reader…" />}>
        <PaperPdfReader
          recordId={recordId}
          document={document}
          scrollToPage={null}
          highlightRegions={NO_REGIONS}
          navKey={`document-${document.kind}-${document.id}`}
          contained={contained}
          fill={fill}
          downloadControl={
            <button
              type="button"
              onClick={save}
              aria-label={`Download ${document.label}`}
              className={cn(PILL_SECONDARY, FOCUS_RING, CONTROL_SIZE, "px-3")}
            >
              <i className="fas fa-download text-2xs" aria-hidden />
              Download
            </button>
          }
        />
      </Suspense>
    </>
  );
}
