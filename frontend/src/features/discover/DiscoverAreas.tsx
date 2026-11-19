import { useEffect, useId } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import type { DiscoverInterests } from "@/types/records";

export interface AreaSelection {
  classification_ids: number[];
  psced_ids: number[];
}

export const NO_AREAS: AreaSelection = { classification_ids: [], psced_ids: [] };

interface DiscoverAreasProps {
  options: DiscoverInterests;
  selection: AreaSelection;
  onSelectionChange: (next: AreaSelection) => void;
  loading: boolean;
  /** Areas could not be read: the message, and no save. */
  loadFailed: string | null;
  /** The last save or reset failed. */
  error: string;
  saving: boolean;
  onSave: () => void;
  resetConfirming: boolean;
  onResetConfirmingChange: (confirming: boolean) => void;
  resetting: boolean;
  onReset: () => void;
}

/**
 * The reader's Areas, as a section of Discover's Filters panel (IR-1188). It was
 * a modal of its own; what it does is unchanged. Areas shape Best, not the
 * catalogue filters above them, so Clear filters never touches them.
 */
export function DiscoverAreas({
  options,
  selection,
  onSelectionChange,
  loading,
  loadFailed,
  error,
  saving,
  onSave,
  resetConfirming,
  onResetConfirmingChange,
  resetting,
  onReset,
}: DiscoverAreasProps) {
  const headingId = useId();
  // Closing the panel abandons a half-made reset, as closing the old modal did.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => () => onResetConfirmingChange(false), []);
  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col gap-4">
      <div>
        <h3 id={headingId} className="text-small font-semibold text-stone-900">Your Areas</h3>
        <p className="mt-1 text-small text-stone-600">
          Choose any Areas you’d like to see more often in Best. Leave this blank to browse the latest research.
        </p>
      </div>
      {loadFailed && <p role="alert" className="text-small text-brand">{loadFailed}</p>}
      {error && <p role="alert" className="text-small text-brand">{error}</p>}
      <AreaChoices title="Research classifications" options={options.classifications} selected={selection.classification_ids}
        onChange={(ids) => onSelectionChange({ ...selection, classification_ids: ids })} />
      <AreaChoices title="PSCED areas" options={options.psced} selected={selection.psced_ids}
        onChange={(ids) => onSelectionChange({ ...selection, psced_ids: ids })} />
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={cn(PILL_PRIMARY, FOCUS_RING)} disabled={saving || loading || Boolean(loadFailed)} onClick={onSave}>
          {loading ? "Loading…" : saving ? "Saving…" : "Save Areas"}
        </button>
        <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)}
          onClick={() => onSelectionChange(NO_AREAS)}>
          Clear areas
        </button>
      </div>
      <div className="border-t border-stone-100 pt-4">
        <p className="text-small text-stone-600">
          Resetting clears your Areas and everything you marked Not interested. Your saved papers and folders stay, and
          the papers you saved still shape Best until you unsave them.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {resetConfirming ? <>
            <button type="button" className={cn(PILL_PRIMARY, FOCUS_RING)} disabled={resetting} onClick={onReset}>
              {resetting ? "Resetting…" : "Reset"}
            </button>
            <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} disabled={resetting} onClick={() => onResetConfirmingChange(false)}>
              Keep my interests
            </button>
          </> : (
            // Disabled while a reset is still running, so reopening the panel cannot start a second one.
            <button type="button" className={cn(PILL_SECONDARY, FOCUS_RING)} disabled={resetting} onClick={() => onResetConfirmingChange(true)}>
              {resetting ? "Resetting…" : "Reset my interests"}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

/** One column at every width: the panel is narrow even on a desktop. */
function AreaChoices({ title, options, selected, onChange }: {
  title: string;
  options: { id: number; name: string }[];
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  return <fieldset className="min-w-0">
    <legend className="text-small font-semibold text-stone-800">{title}</legend>
    {options.length ? <div className="mt-2 grid grid-cols-1 gap-2">
      {options.map((option) => {
        const checked = selected.includes(option.id);
        return <label key={option.id} className="flex min-w-0 items-start gap-2 rounded-control border border-stone-200 p-2.5 text-small text-stone-700">
          <input type="checkbox" checked={checked} onChange={() => onChange(checked ? selected.filter((id) => id !== option.id) : [...selected, option.id])} className={cn("mt-0.5 accent-brand", FOCUS_RING)} />
          <span className="min-w-0 break-words">{option.name}</span>
        </label>;
      })}
    </div> : <p className="mt-2 text-small text-stone-500">No Areas available.</p>}
  </fieldset>;
}
