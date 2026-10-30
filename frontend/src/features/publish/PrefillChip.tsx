/**
 * One suggestion found in the manuscript, offered under its field (IR-409;
 * spec §4.5).
 *
 * It says where the text came from, "Found in your PDF", and nothing about how
 * sure anyone is: Docling gives no confidence, and inventing one is what
 * ADR-008 forbids. Nothing is filled until the author asks. Over a field they
 * typed in, the action reads *Replace with suggestion*, so the choice to
 * discard their own words is spelled out.
 */
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";

interface PrefillChipProps {
  /** The field's name in lower case, which names the group: "Suggested title". */
  field:      string;
  suggestion: string;
  /** The field holds the author's own words. */
  replaces:   boolean;
  onUse:      () => void;
  onDismiss:  () => void;
}

export function PrefillChip({ field, suggestion, replaces, onUse, onDismiss }: PrefillChipProps) {
  return (
    <div role="group" aria-label={`Suggested ${field}`} className="mt-2 rounded-xl border border-stone-200 bg-stone-50 p-3">
      <p className="flex items-center gap-1.5 text-label font-medium text-stone-600">
        <i className="fas fa-file-lines" aria-hidden />
        Found in your PDF
      </p>
      <p className="mt-1 line-clamp-3 whitespace-pre-line text-small text-stone-800">{suggestion}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" onClick={onUse} className={cn(PILL_SECONDARY, FOCUS_RING, "min-h-9 px-4")}>
          {replaces ? "Replace with suggestion" : "Use"}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          className={cn("min-h-9 rounded-full px-4 text-small text-stone-600 hover:text-stone-900", FOCUS_RING)}
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
