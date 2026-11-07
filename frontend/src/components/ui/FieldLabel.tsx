/**
 * A form control's label, shared by `Input` and `Select`.
 *
 * The app marks the *optional* field, never the required one (IR-585). The word
 * sits inside the `<label>`, so it is part of the control's accessible name:
 * "Link (optional)". A required field shows nothing and carries `aria-required`,
 * which a screen reader announces as "required" on its own. A field can also be
 * neither -- sign-in, a search box -- and then it shows nothing at all.
 */
interface FieldLabelProps {
  htmlFor:   string;
  label:     string;
  optional?: boolean;
  /** Spacing only, e.g. `mb-1` above a control that is not in a flex column. */
  className?: string;
}

export function FieldLabel({ htmlFor, label, optional, className = "" }: FieldLabelProps) {
  return (
    <label htmlFor={htmlFor} className={`block text-sm font-medium text-stone-700 ${className}`}>
      {label}
      {/* Stone-600 on white is 7.6:1, so the marker passes 4.5:1 as text. */}
      {optional && (
        <>
          {" "}
          <span className="text-small font-normal text-stone-600">(optional)</span>
        </>
      )}
    </label>
  );
}

/**
 * The two ways a field can be marked, which are never both: a field is either
 * required, optional, or neither. The union makes `required optional` a type
 * error rather than a runtime surprise.
 */
export type FieldMarker =
  | {
      /**
       * Sets `aria-required` and renders nothing. Not the native `required`:
       * that would make an empty field `:invalid`, and announced invalid,
       * before anyone has typed in it.
       */
      required?: boolean;
      optional?: never;
    }
  | {
      /** Renders "(optional)" inside the label, through `FieldLabel`. */
      optional?: boolean;
      required?: never;
    };
