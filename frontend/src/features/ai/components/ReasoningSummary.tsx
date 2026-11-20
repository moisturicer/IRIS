import { useId, useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronRightIcon } from "./AskIrisIcons";

/** The collapsed reasoning summary (IR-596); its body is not rendered until opened. */
export function ReasoningSummary({ summary, compact = false }: { summary?: string; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();

  if (!summary?.trim()) return null;

  return (
    <div className={cn("mb-2", compact ? "mt-0.5" : "mt-1")}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? bodyId : undefined}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-control px-1.5 py-1 -ml-1.5",
          "text-control font-medium text-stone-500 transition-colors",
          "hover:text-stone-700 hover:bg-stone-100",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40",
        )}
      >
        <ChevronRightIcon
          inline
          className={cn("transition-transform duration-200 motion-reduce:transition-none", open && "rotate-90")}
        />
        Reasoning summary
      </button>

      {open && (
        <div
          id={bodyId}
          role="region"
          aria-label="Reasoning summary"
          className={cn(
            "mt-1.5 rounded-control border border-stone-200 bg-stone-50 px-3 py-2.5 text-small leading-relaxed text-stone-600",
          )}
        >
          {summary}
        </div>
      )}
    </div>
  );
}
