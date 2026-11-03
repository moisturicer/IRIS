/**
 * What sits under a field Publish can fill in from the manuscript (IR-409;
 * IR-833).
 *
 * `PrefillChip` offers a value the author has to accept: authors, keywords
 * and publication year always, and a title or abstract that was not filled in
 * — because the field holds the author's own words, or the value is too long.
 * `AutofilledNote` marks a value that *was* filled in, with Undo.
 *
 * Both say where the text came from, "Found in your PDF", and the page when
 * the server knows it, and nothing about how sure anyone is: nothing measures
 * that, and inventing it is what ADR-008 forbids. Over a field the author
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
  page?:      number | null;
  /** Longer than the field allows: the author shortens it after using it. */
  tooLong?:   boolean;
  onUse:      () => void;
  onDismiss:  () => void;
}

function foundIn(page: number | null | undefined) {
  return page != null ? `Found in your PDF, page ${page}` : "Found in your PDF";
}

export function PrefillChip({ field, suggestion, replaces, page, tooLong = false, onUse, onDismiss }: PrefillChipProps) {
  return (
    <div role="group" aria-label={`Suggested ${field}`} className="mt-2 rounded-xl border border-stone-200 bg-stone-50 p-3">
      <p className="flex items-center gap-1.5 text-label font-medium text-stone-600">
        <i className="fas fa-file-lines" aria-hidden />
        {foundIn(page)}
      </p>
      <p className="mt-1 line-clamp-3 whitespace-pre-line text-small text-stone-800">{suggestion}</p>
      {tooLong && (
        <p className="mt-1 text-small text-stone-600">This is longer than the field allows. Shorten it after using it.</p>
      )}
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

interface AutofilledNoteProps {
  field:   string;
  page:    number | null;
  /** The value came from the previous file, which this one did not replace. */
  stale?:  boolean;
  onUndo?: () => void;
}

export function AutofilledNote({ field, page, stale = false, onUndo }: AutofilledNoteProps) {
  return (
    <div role="group" aria-label={`Filled in ${field}`} className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-stone-600">
      <span className="flex items-center gap-1.5">
        <i className="fas fa-file-lines text-label" aria-hidden />
        {stale ? "From your previous file. Check it still applies." : foundIn(page)}
      </span>
      {onUndo && (
        <button type="button" onClick={onUndo} className={cn("rounded-full font-medium text-stone-800 underline underline-offset-2 hover:text-stone-900", FOCUS_RING)}>
          Undo
        </button>
      )}
    </div>
  );
}
