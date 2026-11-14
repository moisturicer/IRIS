import { forwardRef, useId, type ButtonHTMLAttributes } from "react";
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
// "page" is a page action: the 44px pill a dialog footer or an action row
// carries (IR-1088 retired the `PILL_*` class strings for the files it covers).
type Size    = "sm" | "md" | "lg" | "page" | "full" | "icon";

interface BaseButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  /**
   * Why the button is disabled, said beside it (IR-1088): a disabled control
   * with no reason leaves a reader guessing what is missing. Shown only while
   * the button is disabled and not merely busy, and read as its description.
   * It follows the button as a sibling on a line of its own, so the button
   * belongs in a block or a wrapping row, not a row that must not wrap.
   */
  disabledReason?: string;
}

// An icon button has no text of its own, so its accessible name is required
// by the type rather than left to a comment (01-design-system.md section 3).
type ButtonProps =
  | (BaseButtonProps & { size: "icon"; "aria-label": string })
  | (BaseButtonProps & { size?: Exclude<Size, "icon"> });

const VARIANT_CLASSES: Record<Variant, string> = {
  // Tokens, not hex: 01-design-system.md section 2 asks any component being
  // touched to adopt them, and names Button's hardcoded brand as an example.
  primary:   "bg-brand text-white hover:bg-brand-light",
  secondary: "bg-stone-100 text-stone-700 hover:bg-stone-200",
  // Maroon, like primary (IR-359: the palette has no red), so it is told apart
  // by the glyph the component adds below and by the verb the caller writes
  // ("Decline", "Lock"), never by colour alone.
  danger:    "bg-brand-dark text-white hover:bg-brand",
  // `aria-pressed:` for a toggle (IR-352): the attribute selector outranks the
  // base colour whatever the stylesheet order, which a caller's className
  // would not (no tailwind-merge; see the note on Size above).
  ghost:     "text-stone-600 hover:bg-stone-100 aria-pressed:bg-brand-50 aria-pressed:text-brand",
  outline:   "border border-stone-300 text-stone-700 hover:bg-stone-50 disabled:border-stone-200",
};

/**
 * One disabled look for every variant and size (IR-1088, audit CMP-05): Desk
 * Stone fill with Faint Ink text, 3.8:1, rather than the live colour faded by
 * opacity, which left a maroon button at about 2:1 on white. It reads as
 * "not available" by its fill and still reads as a label. Tailwind emits the
 * `disabled:` variant after `hover:`, so a hover never revives it.
 */
const DISABLED_CLASSES =
  "disabled:cursor-not-allowed disabled:bg-stone-200 disabled:text-stone-500 disabled:shadow-none";

// Radius and weight ride on the size, not the base: the pill (`rounded-full`)
// is every text button's shape, and a page action is semibold where the
// compact steps are medium. With no tailwind-merge a base class and a size
// class for the same property would leave stylesheet order to decide.
const SIZE_CLASSES: Record<Size, string> = {
  // The three original steps keep their arbitrary font sizes: the `text-sm`
  // token carries a line-height these don't set, so swapping them would resize
  // every existing button. That retrofit belongs with 01-design-system.md's own
  // "fix the five primitives" task, not with a login fix.
  //
  // `touch:` is the `(pointer: coarse)` media query (tailwind.config.js), so a
  // finger gets 44px at any window width and a mouse never does (IR-1092).
  // `page` and `full` are already `min-h-11` at every width.
  sm:   "rounded-full font-medium px-3 py-1.5 text-[13px] touch:min-h-11",
  md:   "rounded-full font-medium px-4 py-2 text-[14px] touch:min-h-11",
  lg:   "rounded-full font-medium px-5 py-2.5 text-[15px] touch:min-h-11",
  page: "rounded-full font-semibold justify-center min-h-11 px-5 text-sm",
  full: "rounded-full font-medium w-full justify-center min-h-11 px-5 py-3.5 text-md",
  // 44px square on touch-sized screens (12-accessibility.md section 4), 36px
  // beside a desktop pointer: the height of every other control (IR-569). It
  // keeps the 0.75rem radius: DESIGN.md gives reading controls that shape, and
  // a label-less glyph is a different role from a labelled action.
  icon: "rounded-lg font-medium w-11 h-11 lg:w-9 lg:h-9 touch:w-11 touch:h-11 justify-center text-xs",
};

/** The one place a button's look is assembled, for `Button` and `ButtonLink` alike. */
function buttonClasses(variant: Variant, size: Size, className: string): string {
  return `inline-flex items-center gap-2 transition-colors cursor-pointer
          ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${DISABLED_CLASSES} ${className}`;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading, children, className = "", disabled, disabledReason, "aria-describedby": describedBy, ...rest }, ref) => {
    const reasonId = useId();
    const showReason = Boolean(disabled && !loading && disabledReason);
    const button = (
      <button
        ref={ref}
        disabled={disabled || loading}
        aria-describedby={[describedBy, showReason && reasonId].filter(Boolean).join(" ") || undefined}
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
    if (!showReason) return button;
    // A sibling, not a wrapper: the button stays a direct child of its row, so
    // a row that wraps at 360px still wraps. `basis-full` puts the line under
    // the whole row of actions; use the button in a block or wrapping row.
    return (
      <>
        {button}
        <span id={reasonId} className="block w-full basis-full text-small text-stone-600">{disabledReason}</span>
      </>
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
