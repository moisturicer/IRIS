import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "outline";
// "full" is the entry-screen step: full width, a size larger than `lg`, and a
// 44px-tall hit area (12-accessibility.md section 4 adopts 2.5.5).
// It belongs to the primitive rather than to a caller's className because the
// project's class helper is plain clsx with no tailwind-merge -- a caller
// passing `py-3.5` alongside the primitive's `py-2.5` keeps *both*, and
// stylesheet order silently decides which wins.
type Size    = "sm" | "md" | "lg" | "full";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?:    Size;
  loading?: boolean;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  // Tokens, not hex: 01-design-system.md section 2 asks any component being
  // touched to adopt them, and names Button's hardcoded brand as an example.
  primary:   "bg-brand text-white hover:bg-brand-light disabled:opacity-50",
  secondary: "bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50",
  danger:    "bg-red-600 text-white hover:bg-red-700 disabled:opacity-50",
  ghost:     "text-gray-600 hover:bg-gray-100 disabled:opacity-50",
  outline:   "border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50",
};

const SIZE_CLASSES: Record<Size, string> = {
  // The three original steps keep their arbitrary font sizes: the `text-sm`
  // token carries a line-height these don't set, so swapping them would resize
  // every existing button. That retrofit belongs with 01-design-system.md's own
  // "fix the five primitives" task, not with a login fix.
  sm:   "px-3 py-1.5 text-[12px]",
  md:   "px-4 py-2 text-[13px]",
  lg:   "px-5 py-2.5 text-[14px]",
  full: "w-full justify-center min-h-11 px-5 py-3.5 text-md",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, children, className = "", disabled, ...rest }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={`inline-flex items-center gap-2 rounded-lg font-medium transition-colors
          cursor-pointer disabled:cursor-not-allowed
          ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
        {...rest}
      >
        {loading && (
          <svg className="animate-spin h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" aria-hidden focusable={false}>
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";
