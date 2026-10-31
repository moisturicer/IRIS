import { IrisLoader } from "@/components/brand/IrisBrand";

interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE: Record<string, string> = {
  sm: "h-4 w-4",
  md: "h-7 w-7",
  lg: "h-10 w-10",
};

/**
 * A page or panel loading uses the Folio Ribbon loader (IR-744); `sm` stays a
 * plain ring because it sits inside a button beside words like "Deleting…".
 *
 * Decorative either way: every caller says what is loading in its own
 * `role="status"` region, and a second announcement would only repeat it.
 */
export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  if (size !== "sm") {
    return <IrisLoader className={`${SIZE[size]} text-brand ${className}`} />;
  }
  return (
    <svg
      className={`animate-spin motion-reduce:animate-none ${SIZE.sm} text-brand ${className}`}
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden
      focusable={false}
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  );
}
