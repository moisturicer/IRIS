/**
 * What sits under a field Publish can fill in from the manuscript (IR-409;
 * IR-833).
 *
 * `PrefillChip` offers a value the author has to accept: authors, keywords
 * and publication year always, and a title or abstract that was not filled in
 * — because the field holds the author's own words, or the value is too long.
 * `AutofilledNote` marks a value that *was* filled in, with Undo.
 *
 * Both say where the text came from: "Found on page N" when the server knows
 * the page, "Found in your PDF" when it does not, and the PDF's own words when
 * LlamaExtract cited them (IR-846). *Show in PDF* turns the preview to that
 * page and highlights the lines. A confidence is never shown as a number: a
 * value the server marks `low_confidence` says "Check this", and an
 * unmeasured one says nothing (ADR-008). Over a field the author typed in, the
 * action reads *Replace with suggestion*, so the choice to discard their own
 * words is spelled out.
 */
import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import type { SuggestionEntry } from "@/types/records";

import { useShowInPreview } from "./PublishDetailsPreview";

interface PrefillChipProps {
  /** The field's name in lower case, which names the group: "Suggested title". */
  field:      string;
  suggestion: string;
  /** The field holds the author's own words. */
  replaces:   boolean;
  page?:      number | null;
  /** Longer than the field allows: the author shortens it after using it. */
  tooLong?:   boolean;
  /** Where it was found, when the server says (IR-846). */
  entry?:     SuggestionEntry<unknown> | null;
  onUse:      () => void;
  onDismiss:  () => void;
}

function foundIn(page: number | null | undefined) {
  return page != null ? `Found on page ${page}` : "Found in your PDF";
}

function plain(text: string) {
  return text.replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * The PDF's own words, "Check this", and Show in PDF, when the server gave
 * them. The words are quoted only where they differ from the value shown.
 */
function Provenance({ field, entry }: { field: string; entry: SuggestionEntry<unknown> | null | undefined }) {
  const showInPreview = useShowInPreview();
  if (!entry) return null;
  const page = entry.page;
  const shown = Array.isArray(entry.value) ? entry.value.join(", ") : String(entry.value);
  const quote = entry.matching_text && plain(entry.matching_text) !== plain(shown) ? entry.matching_text : null;
  return (
    <>
      {entry.low_confidence && (
        <p className="mt-1 flex items-center gap-1.5 text-small font-medium text-stone-800">
          <i className="fas fa-circle-exclamation text-label" aria-hidden />
          Check this against your PDF.
        </p>
      )}
      {quote && (
        <blockquote className="mt-1 line-clamp-2 border-l-2 border-stone-300 pl-2 text-small italic text-stone-600">
          {quote}
        </blockquote>
      )}
      {showInPreview && page != null && (
        <button
          type="button"
          onClick={() => showInPreview(page, entry.region)}
          aria-label={`Show the ${field} in your PDF, page ${page}`}
          className={cn("mt-1 rounded-full text-small font-medium text-stone-800 underline underline-offset-2 hover:text-stone-900", FOCUS_RING)}
        >
          Show in PDF
        </button>
      )}
    </>
  );
}

export function PrefillChip({ field, suggestion, replaces, page, tooLong = false, entry, onUse, onDismiss }: PrefillChipProps) {
  return (
    <div role="group" aria-label={`Suggested ${field}`} className="mt-2 rounded-xl border border-stone-200 bg-stone-50 p-3">
      <p className="flex items-center gap-1.5 text-label font-medium text-stone-600">
        <i className="fas fa-file-lines" aria-hidden />
        {foundIn(page)}
      </p>
      <p className="mt-1 line-clamp-3 whitespace-pre-line text-small text-stone-800">{suggestion}</p>
      <Provenance field={field} entry={entry} />
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
  entry?:  SuggestionEntry<unknown> | null;
  onUndo?: () => void;
}

export function AutofilledNote({ field, page, stale = false, entry, onUndo }: AutofilledNoteProps) {
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
      {!stale && <div className="basis-full"><Provenance field={field} entry={entry} /></div>}
    </div>
  );
}
