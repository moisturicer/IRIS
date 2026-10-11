import { useId } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import type { RecordVersion } from "@/types/records";

/**
 * The header's version picker (IR-416; ADR-032 §5, spec §4.6/§4.11).
 *
 * Rendered only when the record has two or more versions: with one there is
 * nothing to choose between. The caller decides that, and passes only what
 * the server sent -- `versions` is null to a viewer who may not read the
 * review (IR-479), so a reader of a published paper never sees this.
 *
 * A native `<select>`: it is a single choice from a short list, and the
 * platform's control is the one every keyboard and screen reader already
 * knows. The newest version is the current paper; choosing it clears the
 * choice rather than naming it, so a link to the paper stays the paper.
 */
export function VersionPicker({
  versions,
  viewing,
  onChoose,
  unsubmitted = false,
}: {
  versions: RecordVersion[];
  /** The version being read, or null for the current one. */
  viewing: number | null;
  /** The version chosen, or null for the current one. */
  onChoose: (number: number | null) => void;
  /**
   * The owner's current manuscript is a revision not yet submitted (IR-273).
   * Then the current paper is that upload, offered as its own entry, and the
   * newest version is a version like any other, so it can still be read.
   */
  unsubmitted?: boolean;
}) {
  const id = useId();
  const latest = versions[versions.length - 1];
  // The entry that stands for "the current paper": the newest version, or
  // the owner's unsubmitted revision when there is one.
  const currentValue = unsubmitted ? "" : String(latest.number);

  return (
    <div className="flex items-center gap-2 text-sm">
      <label htmlFor={id} className="font-semibold text-stone-700">
        Version
      </label>
      <select
        id={id}
        value={viewing != null ? String(viewing) : currentValue}
        onChange={(e) => onChoose(e.target.value === currentValue ? null : Number(e.target.value))}
        className={cn(
          "min-h-11 lg:min-h-9 rounded-lg border border-stone-300 bg-white px-2 text-sm text-stone-800",
          FOCUS_RING,
        )}
      >
        {versions.map((v) => {
          const current = !unsubmitted && v.number === latest.number;
          // An earlier version submitted with no manuscript has nothing to open.
          const empty = !v.manuscript_url && !current;
          return (
            <option key={v.number} value={v.number} disabled={empty}>
              {`v${v.number} · ${v.cause_label} · ${formatDate(v.created_at)}`}
              {current ? " (current)" : ""}
              {empty ? " (no manuscript)" : ""}
            </option>
          );
        })}
        {unsubmitted && <option value="">Your revision · not yet submitted (current)</option>}
      </select>
    </div>
  );
}

/**
 * Above the reader while an earlier version is open (IR-416). Says which
 * version this is, offers the way back, and says what does not follow it:
 * citation highlights and Ask IRIS both read the current paper, whose page
 * coordinates an earlier version does not share (ADR-031).
 */
export function VersionBanner({
  viewing,
  latest,
  onBack,
}: {
  viewing: number;
  latest: number;
  onBack: () => void;
}) {
  return (
    <div className="rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 flex items-start gap-3 flex-wrap">
      <i className="fas fa-clock-rotate-left text-sm text-brand mt-0.5" aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold text-stone-900">
          You are viewing v{viewing} of {latest}
        </p>
        <p className="text-stone-700 mt-0.5">
          Citation highlights and Ask IRIS use the current version.
        </p>
      </div>
      <button
        type="button"
        onClick={onBack}
        className={cn("min-h-11 lg:min-h-8 text-sm font-semibold text-brand hover:underline", FOCUS_RING)}
      >
        Back to current
      </button>
    </div>
  );
}
