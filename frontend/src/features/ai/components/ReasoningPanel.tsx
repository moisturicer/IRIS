import { useId, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * The model's working, beside the answer and never inside it (IR-381).
 *
 * Reasoning already arrived on its own channel (IR-327) and was already being
 * relayed to the browser — where it was thrown away. This is where it lands.
 * A reader waiting on a slow answer can watch the model think instead of a
 * spinner, and a reader reopening the conversation weeks later can still see
 * what produced the answer they are reading.
 *
 * **Collapsed by default, for every reader**, live and replayed alike, and
 * expanding it is their choice. The collapsed state is the whole distinction
 * between reasoning and a cited answer: nothing here was scanned for citation
 * markers, nothing here is quotable, and a panel a reader has to open cannot
 * be mistaken for the answer text flowing above it.
 *
 * A real `<button>` with `aria-expanded` and `aria-controls` rather than
 * `<details>`/`<summary>`: keyboard operation and the announced expanded state
 * come from the element itself, and both are reachable through the accessible
 * tree by role and name, which `<summary>`'s role mapping is not reliably.
 */
export function ReasoningPanel({
  reasoning,
  streaming = false,
  compact = false,
}: {
  reasoning: string;
  /** True while deltas are still arriving — the label says so. */
  streaming?: boolean;
  /** Paper Chat's narrower density, matching the bubbles around it. */
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();

  if (!reasoning.trim()) return null;

  return (
    <div className={compact ? "mt-2" : "mt-2.5"}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 -ml-1.5",
          "text-xs font-medium text-stone-500 transition-colors",
          "hover:text-stone-700 hover:bg-stone-100",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
        )}
      >
        <i
          className={cn(
            "fas fa-chevron-right text-2xs transition-transform duration-200 motion-reduce:transition-none",
            open && "rotate-90",
          )}
          aria-hidden
        />
        {streaming ? "Reasoning…" : "Reasoning"}
      </button>

      {/* Rendered only when open: an `aria-hidden` copy left in the tree is
          still text a find-in-page turns up beside the answer. */}
      {open && (
        <div
          id={bodyId}
          role="region"
          aria-label="Reasoning"
          className={cn(
            "mt-1.5 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5",
            "whitespace-pre-wrap text-stone-600",
            compact ? "text-2xs leading-relaxed" : "text-xs leading-relaxed",
          )}
        >
          {reasoning}
        </div>
      )}
    </div>
  );
}
