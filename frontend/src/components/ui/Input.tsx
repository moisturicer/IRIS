import { forwardRef, useId, type InputHTMLAttributes } from "react";

// "lg" is the entry-screen step: a 44px-tall control, per 12-accessibility.md
// section 4, which adopts 2.5.5 because the product is used on phones. Like
// Button's sizes it lives on the primitive, because clsx has no tailwind-merge
// and a caller's `py-3` would not replace the primitive's `py-2` -- both
// survive and stylesheet order decides.
type Size = "md" | "lg";

const SIZE_CLASSES: Record<Size, string> = {
  md: "px-3 py-2 text-[13px]",
  lg: "min-h-11 px-4 py-3 text-base",
};

// `size` is omitted from the native attributes deliberately: HTML's own `size`
// is a character-count number, and letting it through would make `size="lg"`
// silently mean two different things.
interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?:   string;
  error?:   string;
  hint?:    string;
  size?:    Size;
  leading?: React.ReactNode;
  /**
   * Interactive affordance pinned inside the field's trailing edge -- a
   * show/hide password toggle, say. Unlike `leading`, which is decorative and
   * click-through, this stays clickable, so whatever is passed must carry its
   * own accessible name.
   */
  trailing?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      hint,
      size = "md",
      leading,
      trailing,
      className = "",
      id,
      "aria-describedby": describedBy,
      "aria-invalid": ariaInvalid,
      ...rest
    },
    ref,
  ) => {
    // Only used when the caller gave neither an id nor a label to derive one
    // from; a generated id is still better than none, because without it the
    // <label> and the error text have nothing to point at.
    const fallbackId = useId();
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-") ?? fallbackId;
    const errorId = `${inputId}-error`;
    const hintId  = `${inputId}-hint`;

    // A field can be invalid without owning the sentence that explains why:
    // a rejected sign-in is described by one alert above the form, not by a
    // message under each field. Callers say so with a bare `aria-invalid`, and
    // the field must then look and announce invalid just the same.
    const invalid = Boolean(error) || ariaInvalid === true || ariaInvalid === "true";

    // The hint is not rendered while an error is showing, so it must not be
    // referenced then either -- aria-describedby pointing at a missing node is
    // announced as nothing at all in some screen readers.
    const describedByIds = [
      describedBy,
      error ? errorId : null,
      hint && !error ? hintId : null,
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={inputId} className="text-[13px] font-medium text-gray-700">
            {label}
          </label>
        )}
        <div className="relative">
          {leading && (
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-gray-500">
              {leading}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            aria-invalid={invalid ? true : undefined}
            aria-describedby={describedByIds || undefined}
            className={`w-full border rounded-lg outline-none transition-colors
              placeholder:text-gray-500 text-gray-900
              ${SIZE_CLASSES[size]}
              ${leading ? "pl-9" : ""}
              ${trailing ? "pr-16" : ""}
              ${invalid
                ? "border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-500"
                : "border-gray-300 focus:border-brand focus:ring-1 focus:ring-brand"
              }
              disabled:bg-gray-50 disabled:text-gray-500
              ${className}`}
            {...rest}
          />
          {trailing && (
            <div className="absolute inset-y-0 right-0 pr-3 flex items-center">
              {trailing}
            </div>
          )}
        </div>
        {/* red-600 (4.83:1 on white), not red-500 -- red-500 is 3.76:1 and
            fails AA for text this size, which would make the error unreadable
            for exactly the users the association below is for. */}
        {error && <p id={errorId} className="text-[12px] text-red-600">{error}</p>}
        {hint && !error && <p id={hintId} className="text-[12px] text-gray-500">{hint}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
