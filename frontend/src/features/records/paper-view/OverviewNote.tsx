import type { ReactNode } from "react";

/**
 * A quiet, single-line note for an AI Overview that has nothing to show (IR-526).
 *
 * No icon, title or second sentence: a state the reader cannot act on should not take
 * the room of a card. Truncates rather than wrapping so it never exceeds one line.
 * Meant to be reused for other unavailable reasons (IR-564).
 */
export function OverviewNote({ children }: { children: ReactNode }) {
  return <p className="text-xs text-stone-500 truncate">{children}</p>;
}
