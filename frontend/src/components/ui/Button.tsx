import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Link, type LinkProps } from "react-router-dom";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "outline";
// "full" is the entry-screen step: full width, a size larger than `lg`, and a
// 44px-tall hit area (12-accessibility.md section 4 adopts 2.5.5).
// It belongs to the primitive rather than to a caller's className because the
// project's class helper is plain clsx with no tailwind-merge -- a caller
// passing `py-3.5` alongside the primitive's `py-2.5` keeps *both*, and
// stylesheet order silently decides which wins.
// "icon" is a square, label-less button for a toolbar glyph (IR-352); its
// `aria-label` is required by ButtonProps below.
type Size    = "sm" | "md" | "lg" | "full" | "icon";

interface BaseButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

// An icon button has no text of its own, so its accessible name is required
// by the type rather than left to a comment (01-design-system.md section 3).
type ButtonProps =
  | (BaseButtonProps & { size: "icon"; "aria-label": string })
  | (BaseButtonProps & { size?: Exclude<Size, "icon"> });

const VARIANT_CLASSES: Record<Variant, string> = {
  // Tokens, not hex: 01-design-system.md section 2 asks any component being
  // touched to adopt them, and names Button's hardcoded brand as an example.
  primary:   "bg-brand text-white hover:bg-brand-light disabled:opacity-50",
  secondary: "bg-stone-100 text-stone-700 hover:bg-stone-200 disabled:opacity-50",
  // Maroon, like primary (IR-359: the palette has no red), so it is told apart
  // by the glyph the component adds below and by the verb the caller writes
  // ("Decline", "Lock"), never by colour alone.
  danger:    "bg-brand-dark text-white hover:bg-brand disabled:opacity-50",
  // `aria-pressed:` for a toggle (IR-352): the attribute selector outranks the
  // base colour whatever the stylesheet order, which a caller's className
  // would not (no tailwind-merge; see the note on Size above).
  ghost:     "text-stone-600 hover:bg-stone-100 disabled:opacity-50 aria-pressed:bg-brand-50 aria-pressed:text-brand",
  outline:   "border border-stone-300 text-stone-700 hover:bg-stone-50 disabled:opacity-50",
};

const SIZE_CLASSES: Record<Size, string> = {
  // The three original steps keep their arbitrary font sizes: the `text-sm`
  // token carries a line-height these don't set, so swapping them would resize
  // every existing button. That retrofit belongs with 01-design-system.md's own
  // "fix the five primitives" task, not with a login fix.
  sm:   "px-3 py-1.5 text-[13px]",
  md:   "px-4 py-2 text-[14px]",
  lg:   "px-5 py-2.5 text-[15px]",
  full: "w-full justify-center min-h-11 px-5 py-3.5 text-md",
  // 44px square on touch-sized screens (12-accessibility.md section 4), 36px
  // beside a desktop pointer: the height of every other control (IR-569).
  icon: "w-11 h-11 lg:w-9 lg:h-9 justify-center text-xs",
};

/** The one place a button's look is assembled, for `Button` and `ButtonLink` alike. */
function buttonClasses(variant: Variant, size: Size, className: string): string {
  // Entry controls keep readable disabled text (IR-533), rather than fading
  // the entire control below the project's 4.5:1 threshold.
  const variantClasses = size === "full"
    ? VARIANT_CLASSES[variant].replace("disabled:opacity-50", "")
    : VARIANT_CLASSES[variant];
  return `inline-flex items-center gap-2 rounded-lg font-medium transition-colors
          cursor-pointer disabled:cursor-not-allowed
          ${variantClasses} ${SIZE_CLASSES[size]}
          ${size === "full" ? "disabled:bg-stone-100 disabled:text-stone-700" : ""} ${className}`;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, children, className = "", disabled, ...rest }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={buttonClasses(variant, size, className)}
        {...rest}
      >
        {loading && (
          <svg className="animate-spin h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" aria-hidden focusable={false}>
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        )}
        {variant === "danger" && !loading && (
          <i className="fas fa-triangle-exclamation shrink-0" aria-hidden />
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";

interface ButtonLinkProps extends LinkProps {
  variant?: Variant;
  size?: Exclude<Size, "icon">;
}

/**
 * An action that navigates is a link, so assistive technology announces it as
 * one, but it can look like a button (IR-538, the decision IR-213 recorded).
 * It takes the button's variants and size steps from `buttonClasses` rather
 * than having them copied onto an anchor. No `loading` or `disabled`: a link
 * has neither. No `icon` size: an icon link would need its own name contract.
 */
export const ButtonLink = forwardRef<HTMLAnchorElement, ButtonLinkProps>(
  ({ variant = "primary", size = "md", className = "", children, ...rest }, ref) => (
    <Link ref={ref} className={buttonClasses(variant, size, className)} {...rest}>
      {variant === "danger" && <i className="fas fa-triangle-exclamation shrink-0" aria-hidden />}
      {children}
    </Link>
  ),
);

ButtonLink.displayName = "ButtonLink";
