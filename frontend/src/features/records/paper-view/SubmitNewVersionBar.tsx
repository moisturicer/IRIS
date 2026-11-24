import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { cn, joinLabels } from "@/lib/utils";
import type { NewVersionHint } from "@/types/records";
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
 * Grey until there is something to send, solid maroon once there is
 * (ADR-022 Amendment 8, IR-1322): a disabled primary is not a faded maroon,
 * which would still read as the action to take.
 */
const SUBMIT = cn(
  PILL_PRIMARY,
  "shrink-0 justify-center disabled:bg-stone-200 disabled:text-stone-600 disabled:shadow-none disabled:opacity-100",
);

interface SubmitChangesBarProps {
  /** Who asked, each party once ("Adviser", "IERC"). */
  askers: string[];
  /** What is held and not sent yet, by name. */
  changes: string[];
  /**
   * `version` while a revision is open, so the changes go as a new version
   * (`hint` is then required); `documents` otherwise.
   */
  mode: "version" | "documents";
  hint?: NewVersionHint;
  sending?: boolean;
  onSubmit: () => void;
}

/**
 * The top of the Documents tab while reviewers ask for changes (IR-1318,
 * IR-1322): who asked, what the owner has added that nobody has been sent
 * yet, and one Submit at its top right. A revision is answered with *Submit
 * new version*, which opens the page's dialog; documents alone with *Submit
 * added documents*. Nothing reaches a reviewer before that press, so the
 * button stays grey until there is something to send. A reason the server
 * gives for not sending a version yet is shown here and describes the button.
 */
export function SubmitChangesBar({ askers, changes, mode, hint, sending = false, onSubmit }: SubmitChangesBarProps) {
  // A version is held by the server's own reason ("Nothing has changed
  // since…"), which knows about the manuscript and details too; documents
  // are held while none is added.
  const blocked = mode === "version" ? hint?.blocked ?? null : null;
  const nothing = changes.length === 0;
  const empty = mode === "documents" && nothing;
  const reasonId = blocked ? "submit-changes-blocked" : empty ? "submit-changes-empty" : undefined;
  return (
    <section
      aria-labelledby="submit-changes-heading"
      className="flex flex-col gap-3 rounded-card border border-stone-300 bg-surface p-4 sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0 space-y-1">
        <h2 id="submit-changes-heading" className="flex items-center gap-2 text-sm font-bold text-brand-dark">
          <i className={cn("fas text-xs", mode === "version" ? "fa-arrow-rotate-left" : "fa-file-circle-exclamation")} aria-hidden />
          Changes requested by {joinLabels(askers)}
        </h2>
        {!nothing && (
          <p className="text-sm text-stone-800">
            {changes.length === 1 ? "1 change" : `${changes.length} changes`} not sent yet:{" "}
            {joinLabels(changes)}.
          </p>
        )}
        {blocked ? (
          <p id="submit-changes-blocked" className="text-sm text-brand">{blocked}</p>
        ) : empty ? (
          <p id="submit-changes-empty" className="text-sm text-stone-700">
            Upload what was asked for below, then submit it. Nothing is sent until you do.
          </p>
        ) : nothing ? (
          <p className="text-sm text-stone-700">Upload your changes below, then submit them.</p>
        ) : (
          <p className="text-sm text-stone-700">Nothing is sent until you submit.</p>
        )}
        {mode === "version" && hint && <p className="text-xs text-stone-600">{newVersionSummary(hint)}</p>}
      </div>
      <button
        type="button"
        onClick={onSubmit}
        disabled={empty || blocked != null || sending}
        aria-describedby={reasonId}
        className={cn(SUBMIT, FOCUS_RING)}
      >
        <i className={cn("fas text-2xs", sending ? "fa-spinner motion-safe:animate-spin" : "fa-paper-plane")} aria-hidden />
        {mode === "version" ? "Submit new version" : sending ? "Submitting…" : "Submit added documents"}
      </button>
    </section>
  );
}
