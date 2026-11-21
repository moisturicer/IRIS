import { useState } from "react";

import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { PaperSaveDropdown } from "@/features/discover/PaperSaveDropdown";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

interface SaveCiteShareProps {
  record: RecordDetail;
  /** Save is the filled action where there is no paper to view (IR-569). */
  savePrimary: boolean;
  onCite: () => void;
}

/**
 * Save, Cite and Share (IR-1271, moved out of the page unchanged). Share
 * copies the paper's permanent link (IR-356), the address a reader would
 * paste to a colleague. A blocked clipboard claims nothing.
 */
export function SaveCiteShare({ record, savePrimary, onCite }: SaveCiteShareProps) {
  const [shareState, setShareState] = useState<"idle" | "copied" | "failed">("idle");
  const handleShare = async () => {
    let outcome: "copied" | "failed" = "copied";
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/records/${record.id}`);
    } catch {
      // No clipboard (plain http, or permission refused): say so rather
      // than failing silently; the address bar still has the link.
      outcome = "failed";
    }
    setShareState(outcome);
    window.setTimeout(() => setShareState("idle"), 2500);
  };

  return (
    <>
      <PaperSaveDropdown
        record={record}
        variant="pill"
        emphasis={savePrimary ? "primary" : "secondary"}
      />

      <button type="button" onClick={onCite} className={PILL_SECONDARY}>
        <i className="fas fa-quote-right text-2xs" aria-hidden />
        Cite
      </button>

      <button type="button" onClick={handleShare} className={PILL_SECONDARY}>
        <i
          className={cn(
            "fas text-2xs",
            shareState === "copied" ? "fa-check text-brand" : shareState === "failed" ? "fa-circle-exclamation" : "fa-link",
          )}
          aria-hidden
        />
        {shareState === "copied" ? "Link copied" : shareState === "failed" ? "Couldn’t copy" : "Share"}
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {shareState === "copied"
          ? "Link to this paper copied"
          : shareState === "failed"
            ? "Couldn’t copy the link. Copy it from the address bar."
            : ""}
      </span>
    </>
  );
}
