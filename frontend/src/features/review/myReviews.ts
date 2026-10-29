import type { MyReviewsRow, MyReviewsSort, MyReviewsTab, ReviewOutcome } from "@/types/reviews";

/**
 * My Reviews' own small rules (IR-268): the URL contract and how a row is
 * worded. Kept out of the page so they are tested without a DOM.
 */

export const TABS: { key: MyReviewsTab; label: string }[] = [
  { key: "to_review", label: "To review" },
  { key: "in_review", label: "In review" },
  { key: "done",      label: "Done" },
];

/**
 * Done's filters (ADR-032 §9). `revision_requested` is not one: it is the
 * old pipeline's decline, shown on its row and listed under All only.
 */
export const OUTCOME_FILTERS: { key: ReviewOutcome; label: string }[] = [
  { key: "cleared",   label: "Cleared" },
  { key: "finding",   label: "Finding recorded" },
  { key: "accepted",  label: "Accepted" },
  { key: "rejected",  label: "Rejected" },
  { key: "published", label: "Published" },
];

/** The current tabs' orders (IR-622). Soonest due is the default. */
export const SORTS: { key: MyReviewsSort; label: string }[] = [
  { key: "due",     label: "Soonest due" },
  { key: "waiting", label: "Longest waiting" },
];

export interface MyReviewsView {
  tab:     MyReviewsTab;
  outcome: ReviewOutcome | null;
  /** A coordinator's office view; null is your own reviews. */
  office:  string | null;
  /** To review and In review only: Done is always newest first and never overdue. */
  sort:    MyReviewsSort;
  overdue: boolean;
}

/** The retired Review Queue's `?status=`, read once and replaced. */
const LEGACY_STATUS: Record<string, MyReviewsTab> = {
  pending:  "to_review",
  approved: "done",
  declined: "done",
};

function isTab(value: string | null): value is MyReviewsTab {
  return TABS.some((t) => t.key === value);
}

function isFilter(value: string | null): value is ReviewOutcome {
  return OUTCOME_FILTERS.some((f) => f.key === value);
}

/**
 * The view a URL asks for. The URL is untrusted input, so anything unknown
 * reads as the default. `replace` is the canonical search to swap in when the
 * URL used the retired `?status=` vocabulary, else null.
 */
export function readView(params: URLSearchParams): { view: MyReviewsView; replace: string | null } {
  const legacy = params.get("status");
  const rawTab = params.get("tab");
  const tab: MyReviewsTab = isTab(rawTab)
    ? rawTab
    : (legacy && LEGACY_STATUS[legacy]) || "to_review";
  const rawOutcome = params.get("outcome");
  const current = tab !== "done";
  const view: MyReviewsView = {
    tab,
    outcome: !current && isFilter(rawOutcome) ? rawOutcome : null,
    office: params.get("office") || null,
    sort: current && params.get("sort") === "waiting" ? "waiting" : "due",
    overdue: current && params.get("overdue") === "1",
  };
  return { view, replace: legacy != null ? viewSearch(view) : null };
}

/** A view as a search string, leaving every default out. */
export function viewSearch(view: MyReviewsView): string {
  const params = new URLSearchParams();
  if (view.tab !== "to_review") params.set("tab", view.tab);
  if (view.outcome) params.set("outcome", view.outcome);
  if (view.office) params.set("office", view.office);
  if (view.sort !== "due") params.set("sort", view.sort);
  if (view.overdue) params.set("overdue", "1");
  return params.toString();
}

/**
 * The server's due date as a day name, read in Manila, where every deadline
 * falls at 23:59 (ADR-043). This formats an instant the server chose; it
 * computes no date of its own.
 */
const DUE_DAY = new Intl.DateTimeFormat("en-GB", {
  weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Manila",
});

export function dueLabel(dueAt: string): string {
  return `Due ${DUE_DAY.format(new Date(dueAt)).replace(",", "")}`;
}

/**
 * How late a row is, in the working days the server counted. Before a
 * working day has been missed (a weekend after a Friday deadline) it is just
 * Overdue, since "0 working days overdue" reads like a contradiction.
 */
export function overdueLabel(days: number | null): string {
  if (!days) return "Overdue";
  return days === 1 ? "1 working day overdue" : `${days} working days overdue`;
}

/** Who holds a row: the office, then you, a colleague, or nobody yet. */
export function holderLine(row: MyReviewsRow): string {
  if (row.kind === "pool") return `${row.party_label} · Unassigned`;
  if (row.is_mine) return `${row.party_label} · You`;
  return `${row.party_label} · ${row.holder_name ?? "A former member"}`;
}

/** Who sent a row here and why, when the server knows. */
export function routingLine(row: MyReviewsRow): string | null {
  if (row.submitted_by) return `Submitted by ${row.submitted_by}`;
  const reason = row.routed_reason ? ` · “${row.routed_reason}”` : "";
  if (row.routed_by) return `Routed by ${row.routed_by}${reason}`;
  if (row.routed_reason) return `Handed back by IRIS${reason}`;
  return null;
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

export const WAITING_ON_LABEL: Record<NonNullable<MyReviewsRow["waiting_on"]>, string> = {
  author:   "Waiting on author",
  document: "Waiting on document",
};
