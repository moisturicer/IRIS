import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";

import { FieldLabel, type FieldMarker } from "./FieldLabel";

// The same steps as Input's, so a select beside a text field is the same
// height and type size (IR-539). They live on the primitive for Input's reason:
// clsx has no tailwind-merge, so a caller's padding would not replace these.
// `pr-10` leaves room for the chevron at both steps. "sm" (IR-585) is the
// 36px toolbar step -- Sort and Folder in the library -- where a select sits in
// a row of controls rather than in a form, so it has no Input beside it. It is
// below 12-accessibility.md section 4's 44px target: the toolbar's own controls
// are 36px and the old selects were too, so this keeps the row even and leaves
// the gap visible in one place for the toolbar to close.
type Size = "sm" | "md" | "lg";

// `chevron` is the drawn arrow's right padding, kept beside the control's own
// so a new step is added in one place.
const SIZES: Record<Size, { control: string; chevron: string }> = {
  sm: { control: "min-h-9 pl-2 pr-8 py-1 text-small",  chevron: "pr-2.5" },
  md: { control: "pl-3 pr-10 py-2 text-body",        chevron: "pr-4" },
  lg: { control: "min-h-11 pl-4 pr-10 py-3 text-base", chevron: "pr-4" },
};

// `size` is omitted from the native attributes for Input's reason: HTML's own
// `size` on a select is a visible-row count, not a size step.
type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, "size" | "required"> & FieldMarker & {
  label?:    string;
  error?:    string;
  hint?:     ReactNode;
  size?:     Size;
  /**
   * Puts the label beside the control instead of above it, for a toolbar
   * (IR-585). The error and hint still sit underneath.
   */
  inline?:   boolean;
  /** The `<option>`s and `<optgroup>`s. */
  children:  ReactNode;
};

/**
 * A native `<select>` with Input's contract (IR-539): a label tied to it by a
 * derived id, the error or hint as its accessible description, and
 * `aria-invalid` while it has an error. It stays native rather than a custom
 * listbox so the keyboard, the phone's picker and `<optgroup>` work as each
 * platform expects, with nothing to re-implement.
 */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      error,
      hint,
      size = "md",
      inline = false,
      required,
      optional,
      className = "",
      id,
      children,
      "aria-describedby": describedBy,
      "aria-invalid": ariaInvalid,
      ...rest
    },
    ref,
  ) => {
    const fallbackId = useId();
    const selectId = id ?? label?.toLowerCase().replace(/\s+/g, "-") ?? fallbackId;
    const errorId = `${selectId}-error`;
    const hintId  = `${selectId}-hint`;

    const invalid = Boolean(error) || ariaInvalid === true || ariaInvalid === "true";

    // As in Input: the hint is not rendered under an error, so it is not
    // referenced then either.
    const describedByIds = [
      describedBy,
      error ? errorId : null,
      hint && !error ? hintId : null,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div className="flex flex-col gap-1">
        <div className={inline ? "flex items-center gap-2" : "flex flex-col gap-1"}>
          {label && <FieldLabel htmlFor={selectId} label={label} optional={optional} />}
          <div className="relative">
            <select
              ref={ref}
              id={selectId}
              aria-invalid={invalid ? true : undefined}
              aria-describedby={describedByIds || undefined}
              aria-required={required || undefined}
              className={`w-full appearance-none border rounded-lg bg-surface outline-none transition-colors
                text-stone-900 cursor-pointer
                ${SIZES[size].control}
                ${invalid
                  ? "border-brand focus:border-brand focus:ring-2 focus:ring-brand"
                  : "border-stone-300 focus:border-brand focus:ring-1 focus:ring-brand"
                }
                disabled:cursor-not-allowed disabled:bg-stone-50 disabled:text-stone-500
                ${className}`}
              {...rest}
            >
              {children}
            </select>
            {/* `appearance-none` removes the platform arrow, so one is drawn. It
                is decoration: the combobox role already says it opens. */}
            <span
              aria-hidden
              className={`pointer-events-none absolute inset-y-0 right-0 flex items-center ${SIZES[size].chevron} text-xs text-stone-500`}
            >
              <i className="fas fa-chevron-down" />
            </span>
          </div>
        </div>
        {error && (
          <p id={errorId} className="flex items-start gap-1.5 text-small text-brand">
            <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
            {error}
          </p>
        )}
        {hint && !error && <p id={hintId} className="text-small text-stone-500">{hint}</p>}
      </div>
    );
  }
);

Select.displayName = "Select";
