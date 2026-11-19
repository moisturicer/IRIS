/**
 * A Template's file, always downloaded (ADR-063 decision 8), with a failure
 * said beside it. Guidelines, Publish's Documents step, the Documents tab and
 * a document request all show a Template through this one control.
 */
import { useState } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { errorDetail } from "@/lib/errorDetail";
import { cn, downloadBlob } from "@/lib/utils";

export function TemplateDownload({ fileName, label, download }: {
  fileName: string;
  /** The accessible name: what it is and the file, e.g. "Download the Release Form Template, release.docx". */
  label: string;
  download: () => Promise<{ data: Blob }>;
}) {
  const [problem, setProblem] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const save = async () => {
    setProblem(null);
    setWorking(true);
    try {
      const { data } = await download();
      downloadBlob(data, fileName);
    } catch (err) {
      setProblem(errorDetail(err, "The Template didn't download. Try again."));
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2 text-small text-stone-700">
        <i className="fas fa-file-arrow-down text-stone-500" aria-hidden />
        <button
          type="button"
          onClick={() => void save()}
          disabled={working}
          aria-label={label}
          className={cn("break-all rounded-control text-left font-medium text-brand underline underline-offset-2 disabled:opacity-60", FOCUS_RING)}
        >
          {fileName}
        </button>
      </div>
      {problem && <p role="alert" className="text-small text-brand">{problem}</p>}
    </div>
  );
}
