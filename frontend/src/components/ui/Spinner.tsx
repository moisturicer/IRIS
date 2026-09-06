interface SpinnerProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE: Record<string, string> = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
};

export function Spinner({ size = "md", className = "" }: SpinnerProps) {
  return (
    <svg
      className={`animate-spin ${SIZE[size]} text-[#6B0F12] ${className}`}
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
