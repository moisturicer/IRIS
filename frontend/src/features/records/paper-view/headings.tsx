import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The Paper View's two heading styles (IR-356), one component each so every
 * section reads the same.
 */

/** A section of the reading column: serif, like a printed paper's. */
export function SectionHeading({ children }: { children: ReactNode }) {
  return <h2 className="font-display text-xl font-semibold text-stone-900 mb-2">{children}</h2>;
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
    <h2 id={id} className={cn("text-2xs font-semibold uppercase tracking-[0.14em] text-stone-600", className)}>
      {children}
    </h2>
  );
}
