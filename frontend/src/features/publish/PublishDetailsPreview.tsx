import { useRef, useState, type ReactNode } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import { PaperPdfReader } from "@/features/records/paper-view/PaperPdfReader";

type PublishPane = "details" | "preview";

interface PublishDetailsPreviewProps {
  recordId: number;
  /**
   * Bumped only after the server accepts a replacement Manuscript. The reader
   * remounts on that boundary, so an old fetch cannot paint over the new source.
   */
  sourceKey: number;
  children: ReactNode;
}

/**
 * IR-834: read the server-accepted Manuscript beside the existing Details form.
 *
 * The preview deliberately reuses PaperPdfReader rather than a local-file URL
 * or iframe. PaperPdfReader fetches `/records/:id/manuscript/` through the
 * authenticated API client and owns abort/disposal/retry for those bytes.
 */
export function PublishDetailsPreview({
  recordId,
  sourceKey,
  children,
}: PublishDetailsPreviewProps) {
  const [pane, setPane] = useState<PublishPane>("details");
  const detailsRef = useRef<HTMLElement>(null);
  const previewRef = useRef<HTMLElement>(null);

  function choosePane(next: PublishPane) {
    setPane(next);
    requestAnimationFrame(() => {
      if (next === "preview") {
        previewRef.current?.focus();
        return;
      }

      detailsRef.current
        ?.querySelector<HTMLElement>(
          'input:not([disabled]), textarea:not([disabled]), select:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )
        ?.focus();
    });
  }

  return (
    <div className="space-y-section-sm">
      <div
        role="group"
        aria-label="Details and Manuscript preview"
        className="grid grid-cols-2 gap-2 lg:hidden"
      >
        <button
          type="button"
          aria-pressed={pane === "details"}
          aria-controls="publish-details-panel"
          onClick={() => choosePane("details")}
          className={cn(pane === "details" ? PILL_PRIMARY : PILL_SECONDARY, FOCUS_RING, "w-full")}
        >
          Details
        </button>
        <button
          type="button"
          aria-pressed={pane === "preview"}
          aria-controls="publish-preview-panel"
          onClick={() => choosePane("preview")}
          className={cn(pane === "preview" ? PILL_PRIMARY : PILL_SECONDARY, FOCUS_RING, "w-full")}
        >
          Preview
        </button>
      </div>

      <div className="lg:grid lg:grid-cols-[minmax(0,1.08fr)_minmax(22rem,0.92fr)] lg:items-start lg:gap-section">
        <section
          id="publish-preview-panel"
          ref={previewRef}
          role="region"
          aria-label="Manuscript preview"
          tabIndex={-1}
          className={cn(
            "min-w-0 flex-col overflow-hidden rounded-xl border border-stone-200 bg-surface outline-none",
            "focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
            "h-[calc(100dvh-13rem)] min-h-[20rem] max-h-[44rem]",
            pane === "preview" ? "flex" : "hidden",
            "lg:order-1 lg:flex lg:h-[min(68vh,44rem)]",
          )}
        >
          <div className="shrink-0 border-b border-stone-200 px-4 py-3">
            <h3 className="text-heading font-semibold text-stone-900">Manuscript preview</h3>
            <p className="mt-0.5 text-small text-stone-600">
              This is the file IRIS accepted from the server.
            </p>
          </div>
          <div className="flex min-h-0 flex-1 [container-type:inline-size] [container-name:reading]">
            <PaperPdfReader
              key={`publish:${recordId}:${sourceKey}`}
              recordId={recordId}
              scrollToPage={null}
              highlightRegions={[]}
              navKey={`publish:${recordId}:${sourceKey}`}
              contained
              fill
            />
          </div>
        </section>

        <section
          id="publish-details-panel"
          ref={detailsRef}
          aria-label="Details"
          className={cn("min-w-0", pane === "details" ? "block" : "hidden", "lg:order-2 lg:block")}
        >
          {children}
        </section>
      </div>
    </div>
  );
}
