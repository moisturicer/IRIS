import { TONES } from "@/components/ui/statusTones";

type BadgeVariant = "default" | "success" | "warning" | "danger" | "info" | "neutral";

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

// By meaning, onto the four shared tones (IR-359). The palette has one grey, so
// `default`, `info` and `neutral` all read as quiet: a badge always carries its
// own label, and that label is what tells one from another.
const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  default: TONES.quiet,
  success: TONES.settled,
  warning: TONES.active,
  danger:  TONES.attention,
  info:    TONES.quiet,
  neutral: TONES.quiet,
};

export function Badge({ variant = "default", children, className = "" }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium
        ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
