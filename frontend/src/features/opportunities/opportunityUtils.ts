import type { Opportunity, OpportunityType } from "@/types/opportunities";

/**
 * Filter tabs, in the order the board shows them.
 *
 * `null` is the "All Deadlines" tab rather than a fifth type, so the tab list
 * and the type list stay one array instead of two that can drift.
 */
export const TYPE_TABS: { id: OpportunityType | null; label: string }[] = [
  { id: null,                   label: "All Deadlines"       },
  { id: "internal_call",        label: "Internal Calls"      },
  { id: "conference_deadline",  label: "Conference Deadlines" },
  { id: "funding_window",       label: "Funding Windows"     },
  { id: "institutional_grant",  label: "Institutional Grants" },
];

/**
 * One colour per type, solid so the type reads at a glance down a column of
 * cards. These are the card's loudest element by design: on a deadline board
 * "what kind of thing is this" is the first question, ahead of the title.
 */
export const TYPE_BADGE_CLASS: Record<OpportunityType, string> = {
  institutional_grant: "bg-brand text-white",
  funding_window:      "bg-slate-900 text-white",
  conference_deadline: "bg-brand-100 text-brand-700 border border-brand-200",
  internal_call:       "bg-amber-100 text-amber-900 border border-amber-200",
};

/**
 * The countdown chip.
 *
 * Deliberately not one flat style for every card: this surface exists to
 * answer "what closes soon", so urgency is encoded in colour rather than left
 * for the reader to work out by subtracting dates. Under a week goes red,
 * under three weeks amber, everything else stays quiet.
 */
export function countdownChip(o: Opportunity): { label: string; className: string } {
  if (o.is_closed) {
    return { label: "Closed", className: "bg-stone-100 text-stone-500 border border-stone-200" };
  }
  if (o.days_left === 0) {
    return { label: "Due today", className: "bg-red-50 text-red-700 border border-red-200" };
  }
  const label = `${o.days_left}d left`;
  if (o.days_left <= 7)  return { label, className: "bg-red-50 text-red-700 border border-red-200" };
  if (o.days_left <= 21) return { label, className: "bg-amber-50 text-amber-800 border border-amber-200" };
  return { label, className: "bg-white text-stone-600 border border-stone-200" };
}

/** Peso ceiling, or null when the type has no meaningful ceiling. */
export function formatCeiling(value: string | null): string | null {
  if (value === null || value === "") return null;
  const amount = Number(value);
  if (!Number.isFinite(amount)) return null;
  return `₱${amount.toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;
}

export function formatDueDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-PH", { year: "numeric", month: "short", day: "numeric" });
}

/** Case-insensitive match across the fields a reader would actually search. */
export function matchesQuery(o: Opportunity, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [o.title, o.posting_office, o.audience, o.description, ...o.tags]
    .some((field) => (field ?? "").toLowerCase().includes(q));
}
