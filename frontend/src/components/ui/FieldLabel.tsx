/**
 * A form control's label row, shared by `Input` and `Select` (IR-539).
 *
 * The "(required)" word sits beside the `<label>`, not inside it, and is
 * hidden from assistive technology: the control carries `aria-required`, which
 * a screen reader announces as "required" on its own. Inside the label it would
 * be read twice, and would make every accessible name end in "(required)".
 */
interface FieldLabelProps {
  htmlFor:   string;
  label:     string;
  required?: boolean;
}

export function FieldLabel({ htmlFor, label, required }: FieldLabelProps) {
  return (
    <div className="flex items-baseline gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium text-stone-700">
        {label}
      </label>
      {/* Stone-600 on white is 7.6:1, so the marker passes 4.5:1 as text. */}
      {required && (
        <span aria-hidden className="text-small text-stone-600">
          (required)
        </span>
      )}
    </div>
  );
}
