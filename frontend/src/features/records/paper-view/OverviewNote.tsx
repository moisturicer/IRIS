import type { ReactNode } from "react";

/**
 * A quiet, single-line note for an AI Overview that has nothing to show (IR-526).
 *
 * No icon, title or second sentence: a state the reader cannot act on should not take
 * the room of a card. It wraps when the box is narrow (the Full Text Rule, IR-1219).
 * Meant to be reused for other unavailable reasons (IR-564).
 */
export function OverviewNote({ children }: { children: ReactNode }) {
  return <p className="break-words text-xs text-stone-500">{children}</p>;
}
