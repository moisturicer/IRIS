import { forwardRef, useId, type InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?:   string;
  error?:   string;
  hint?:    string;
  leading?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      hint,
      leading,
      className = "",
      id,
      "aria-describedby": describedBy,
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
            aria-invalid={error ? true : undefined}
            aria-describedby={describedByIds || undefined}
            className={`w-full border rounded-lg text-[13px] px-3 py-2 outline-none transition-colors
              placeholder:text-gray-500 text-gray-900
              ${leading ? "pl-9" : ""}
              ${error
                ? "border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-500"
                : "border-gray-300 focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
              }
              disabled:bg-gray-50 disabled:text-gray-500
              ${className}`}
            {...rest}
          />
        </div>
        {error && <p id={errorId} className="text-[12px] text-red-500">{error}</p>}
        {hint && !error && <p id={hintId} className="text-[12px] text-gray-500">{hint}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";
