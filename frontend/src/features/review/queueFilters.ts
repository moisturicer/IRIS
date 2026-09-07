import type { QueueFilter } from "@/api/reviews";

/**
 * The queue's own small rules, kept out of the component so they can be tested
 * without a DOM (IR-143) — the same reason `lib/access.ts` is a separate module.
 */

export function isQueueFilter(value: string | null): value is QueueFilter {
  return value === "pending" || value === "approved" || value === "declined";
}

/**
 * How a wait is worded. "Today" rather than "0 days", because a queue that
 * says a record has waited zero days reads like a bug.
 */
export function waitLabel(days: number): string {
  if (days <= 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

/**
 * Escalation thresholds. A week is a nudge, a fortnight is a problem — the only
 * genuinely urgent signal in a list where every row otherwise looks identical.
 * Returned as a class name so the *word* still carries the meaning; colour
 * alone would say nothing to a screen reader.
 */
export function waitTone(days: number): string {
  if (days >= 14) return "text-red-700 font-bold";
  if (days >= 7) return "text-amber-700 font-semibold";
  return "text-stone-500";
}
