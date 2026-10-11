/** The three tabs of My Reviews (ADR-032 §9). */
export type MyReviewsTab = "to_review" | "in_review" | "done";

/**
 * A Done row's outcome (ADR-032 §9 Amendment, 2026-10-08), derived by the
 * server from the reviewer's own verdict. `revision_requested` is the old
 * pipeline's decline: shown, but never a filter.
 */
export type ReviewOutcome =
  | "cleared" | "finding" | "accepted" | "rejected" | "published" | "revision_requested";

/**
 * The parties a My Reviews row names. No `intake`: it is retired, and the
 * server shows a historical intake decision as RDCO's.
 */
export type MyReviewsParty = "adviser" | "itso" | "ierc" | "ktto" | "rdco";

/**
 * One row of My Reviews (`GET /reviews/mine/`, IR-268).
 *
 * - `seat`: a reviewer's part, theirs or (in a coordinator's office view) a colleague's;
 * - `pool`: an office's unclaimed record, which carries the `assignment` that
 *   *Claim* and *Assign* address;
 * - `review`: a Done decision with no seat behind it, from before seats existed.
 *
 * Every label is server-worded.
 */
export interface MyReviewsRow {
  key:              string;
  kind:             "seat" | "pool" | "review";
  record:           number;
  title:            string;
  record_type_name: string | null;
  party:            MyReviewsParty;
  party_label:      string;
  seat:             number | null;
  assignment:       number | null;
  holder:           number | null;
  holder_name:      string | null;
  is_mine:          boolean;
  routed_by:        string | null;
  routed_reason:    string;
  submitted_by:     string | null;
  waiting_since:    string | null;
  waiting_days:     number | null;
  /** The record waits on its author, or on a requested document. Record-level. */
  waiting_on:       "author" | "document" | null;
  outcome:          ReviewOutcome | null;
  outcome_label:    string | null;
  decided_at:       string | null;
  can_claim:        boolean;
  can_assign:       boolean;
}

export interface MyReviewsPage {
  rows:   MyReviewsRow[];
  /** Every tab's size in this view. The office view narrows them; the outcome filter never does. */
  counts: Record<MyReviewsTab, number>;
  /** The next page of Done, or null. */
  next:   string | null;
}

export interface MyReviewsQuery {
  tab:      MyReviewsTab;
  outcome?: ReviewOutcome | null;
  office?:  string | null;
  cursor?:  string | null;
}
