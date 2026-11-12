import { useId, useRef, useState } from "react";

import { recordsApi } from "@/api/records";
import { ProgressBar, toPercent } from "@/components/shared/ProgressBar";
import { COLOUR_TRANSITION } from "@/components/ui/interaction";
import { errorDetail } from "@/lib/errorDetail";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";

const PDF_LIMIT = 50 * 1024 * 1024;

interface RevisionManuscriptUploadProps {
  recordId: number;
  /** The record already stores a revised manuscript no version carries yet. */
  staged: boolean;
  /** Told once the file is stored, so the page can re-read the record. */
  onUploaded: () => void | Promise<void>;
}

/**
 * Send the revised manuscript from the *Revision requested* card itself
 * (IR-273), the way an owner sends a requested document from its row: one
 * compact button, a progress bar while it goes, and a toast if it fails.
 * Nothing here decides who may upload -- the page renders it only for the
 * `replace_manuscript` capability, and the server re-checks.
 *
 * The upload is stored, not submitted: reviewers keep reading the submitted
 * manuscript until the owner uses *Submit new version*. A second upload
 * replaces the first, so the button reads *Replace* once one is staged.
 */
export function RevisionManuscriptUpload({ recordId, staged, onUploaded }: RevisionManuscriptUploadProps) {
  const inputId = useId();
  const addToast = useUIStore((s) => s.addToast);
  const [progress, setProgress] = useState<number | null>(null);
  const [fileName, setFileName] = useState("");
  /** Set synchronously, so a second pick before the re-render cannot send twice. */
  const inFlight = useRef(false);

  const send = async (file: File) => {
    if (inFlight.current) return;
    if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") {
      addToast({
        type: "error",
        persist: true,
        message: `${file.name} is not a PDF. Upload the revised manuscript as a PDF.`,
      });
      return;
    }
    if (file.size > PDF_LIMIT) {
      addToast({
        type: "error",
        persist: true,
        message: `${file.name} is larger than 50 MB. Upload a smaller PDF.`,
      });
      return;
    }
    inFlight.current = true;
    setFileName(file.name);
    setProgress(0);
    try {
      await recordsApi.uploadManuscript(recordId, file, { onProgress: setProgress });
    } catch (err) {
      inFlight.current = false;
      setProgress(null);
      addToast({
        type: "error",
        persist: true,
        message: errorDetail(err, `${file.name} could not be uploaded. Please try again.`),
      });
      return;
    }
    inFlight.current = false;
    setProgress(null);
    addToast({ type: "success", message: `${file.name} uploaded. It goes out with your new version.` });
    // Outside the try: the file is already stored, so a failed refresh is not an upload failure.
    await onUploaded();
  };

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      {progress !== null ? (
        <span className="inline-flex items-center gap-2">
          <ProgressBar
            label={`Uploading ${fileName}`}
            progress={progress}
            className="h-1.5 w-28 bg-brand-100"
          />
          <span className="text-2xs font-semibold text-stone-600 tabular-nums" aria-hidden>
            {toPercent(progress)}%
          </span>
        </span>
      ) : (
        <label
          htmlFor={inputId}
          className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-brand-200 text-brand-dark text-xs font-bold cursor-pointer hover:bg-brand-100",
            COLOUR_TRANSITION,
            "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-brand has-[:focus-visible]:ring-offset-2",
          )}
        >
          <i className="fas fa-upload text-2xs" aria-hidden />
          {staged ? "Replace revised manuscript" : "Upload revised manuscript"}
          <input
            id={inputId}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void send(file);
            }}
          />
        </label>
      )}
      {staged && progress === null && (
        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-stone-700">
          <i className="fas fa-file-pen text-2xs text-brand" aria-hidden />
          Revised manuscript ready, not yet submitted
        </span>
      )}
    </div>
  );
}
