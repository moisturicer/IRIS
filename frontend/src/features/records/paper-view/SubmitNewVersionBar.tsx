import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { cn, joinLabels } from "@/lib/utils";
import type { NewVersionHint, OpenRevisionRequest } from "@/types/records";
import { newVersionSummary } from "./NewVersionDialog";

/** The changes a new version would carry, in the bar's words, each once. */
export function unsentChanges(hint: NewVersionHint): string[] {
  const unsent = hint.unsent;
  if (!unsent) return [];
  const named = [
    ...(unsent.manuscript ? ["revised manuscript"] : []),
    ...(unsent.details ? ["edited details"] : []),
    ...unsent.uploads.map((u) => u.label),
  ];
  return [...new Set(named)];
}

/**
 * The top of the Documents tab while a revision is asked for (IR-1318): who
 * asked, what has changed that no version carries yet, and *Submit new
 * version* at its top right, so the owner uploads and sends in one place.
 * The button opens the page's dialog (`NewVersionDialog`), which re-checks
 * everything; a reason the server gives for not sending yet is shown here
 * first and describes the button.
 */
export function SubmitNewVersionBar({
  requests,
  hint,
  onSubmit,
}: {
  requests: OpenRevisionRequest[];
  hint: NewVersionHint;
  onSubmit: () => void;
}) {
  const askers = joinLabels([...new Set(requests.map((r) => r.label))]);
  const changes = unsentChanges(hint);
  return (
    <section
      aria-labelledby="submit-new-version-heading"
      className="flex flex-col gap-3 rounded-card border border-stone-300 bg-surface p-4 sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0 space-y-1">
        <h2 id="submit-new-version-heading" className="flex items-center gap-2 text-sm font-bold text-brand-dark">
          <i className="fas fa-arrow-rotate-left text-xs" aria-hidden />
          Revision requested by {askers}
        </h2>
        {changes.length > 0 && (
          <p className="text-sm text-stone-800">
            {changes.length === 1 ? "1 change" : `${changes.length} changes`} not sent yet:{" "}
            {joinLabels(changes)}.
          </p>
        )}
        {hint.blocked ? (
          <p id="new-version-blocked" className="text-sm text-brand">{hint.blocked}</p>
        ) : changes.length === 0 && (
          <p className="text-sm text-stone-700">Upload your changes below, then submit them.</p>
        )}
        <p className="text-xs text-stone-600">{newVersionSummary(hint)}</p>
      </div>
      <button
        type="button"
        onClick={onSubmit}
        aria-describedby={hint.blocked ? "new-version-blocked" : undefined}
        className={cn(PILL_PRIMARY, "shrink-0 justify-center", FOCUS_RING)}
      >
        <i className="fas fa-paper-plane text-2xs" aria-hidden />
        Submit new version
      </button>
    </section>
  );
}

/**
 * The top of the Documents tab when reviewers asked for documents and no
 * revision is open (IR-1318): an upload is the answer, so there is nothing
 * to submit, and the owner is told so.
 */
export function DocumentsAskedNote({ askers, count }: { askers: string[]; count: number }) {
  return (
    <p className="flex items-center gap-2 rounded-card border border-stone-300 bg-surface p-4 text-sm text-stone-800">
      <i className="fas fa-file-circle-exclamation text-xs text-brand-dark" aria-hidden />
      {joinLabels(askers)} asked for {count === 1 ? "1 document" : `${count} documents`}. Each is sent as
      soon as you upload it.
    </p>
  );
}
