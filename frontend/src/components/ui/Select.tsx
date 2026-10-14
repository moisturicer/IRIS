import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";

import { FieldLabel } from "./FieldLabel";

// The same steps as Input's, so a select beside a text field is the same
// height and type size (IR-539). They live on the primitive for Input's reason:
// clsx has no tailwind-merge, so a caller's padding would not replace these.
// `pr-10` leaves room for the chevron at both steps.
type Size = "md" | "lg";

const SIZE_CLASSES: Record<Size, string> = {
  md: "pl-3 pr-10 py-2 text-[14px]",
  lg: "min-h-11 pl-4 pr-10 py-3 text-base",
};

// `size` is omitted from the native attributes for Input's reason: HTML's own
// `size` on a select is a visible-row count, not a size step.
interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  label?:    string;
  error?:    string;
  hint?:     ReactNode;
  size?:     Size;
  /** As on Input: "(required)" beside the label, and `aria-required`. */
  required?: boolean;
  /** The `<option>`s and `<optgroup>`s. */
  children:  ReactNode;
}

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
      required,
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
        {label && <FieldLabel htmlFor={selectId} label={label} required={required} />}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            aria-invalid={invalid ? true : undefined}
            aria-describedby={describedByIds || undefined}
            aria-required={required || undefined}
            className={`w-full appearance-none border rounded-lg bg-surface outline-none transition-colors
              text-stone-900 cursor-pointer
              ${SIZE_CLASSES[size]}
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
            className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-4 text-xs text-stone-500"
          >
            <i className="fas fa-chevron-down" />
          </span>
        </div>
        {error && (
          <p id={errorId} className="flex items-start gap-1.5 text-[13px] text-brand">
            <i className="fas fa-circle-exclamation mt-0.5 shrink-0" aria-hidden />
            {error}
          </p>
        )}
        {hint && !error && <p id={hintId} className="text-[13px] text-stone-500">{hint}</p>}
      </div>
    );
  }
);

Select.displayName = "Select";
