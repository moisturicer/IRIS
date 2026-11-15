import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The Paper View's two heading styles (IR-356), one component each so every
 * section reads the same.
 */

/**
 * A section of the reading column: serif, like a printed paper's. 22 px, the
 * top of the page's fixed 22 / 17 px ladder (IR-1089); a heading inside a
 * section, such as the AI Overview's, is 17 px.
 */
export function SectionHeading({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="font-display text-section font-semibold text-stone-900 mb-2">
      {children}
    </h2>
  );
}

/** A side card's label: small tracked capitals, quieter than the paper. */
export function RailHeading({
  children,
  id,
  className,
}: {
  children: ReactNode;
  id?: string;
  className?: string;
}) {
  return (
    <h2 id={id} className={cn("text-2xs font-semibold text-stone-600", className)}>
      {children}
    </h2>
  );
}
