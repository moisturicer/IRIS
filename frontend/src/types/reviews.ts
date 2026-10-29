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
  /**
   * The assignment's clock (ADR-043, IR-619): null when its office has no
   * turnaround configured, and on a Done decision with no seat behind it.
   */
  due_at:           string | null;
  original_due_at:  string | null;
  /** The server's verdict; a paused or closed assignment is never overdue. */
  is_overdue:       boolean;
  clock_paused:     boolean;
  /** Manila working days late, holidays excluded (IR-622); null unless overdue. */
  overdue_days:     number | null;
}

/** The current tabs' orders (IR-622). Done is always newest first. */
export type MyReviewsSort = "due" | "waiting";

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
  /** To review and In review only; the server refuses both on Done. */
  sort?:    MyReviewsSort | null;
  overdue?: boolean;
}

/**
 * One row of the coordinator console (`GET /reviews/office/`, IR-623): an
 * unfinished seat, or (`kind: "pool"`) an assignment nobody holds yet. The
 * due date and overdue state are the server's (ADR-043); nothing is worked
 * out here.
 */
export interface OfficeConsoleRow {
  key:              string;
  kind:             "seat" | "pool";
  record:           number;
  title:            string;
  assignment:       number;
  seat:             number | null;
  reviewer:         number | null;
  reviewer_name:    string | null;
  seat_state:       "assigned" | "in_review" | null;
  seat_state_label: string | null;
  /** When the office received the record: its clock's start. */
  opened_at:        string;
  due_at:           string | null;
  original_due_at:  string | null;
  is_overdue:       boolean;
  /** Waiting on a requested document or on the author: the clock stands still. */
  clock_paused:     boolean;
  can_extend:       boolean;
}

/** One member's load in the console: every member, idle ones too. */
export interface OfficeLoad {
  reviewer: number;
  name:     string;
  open_count: number;
  overdue:  number;
}

export interface OfficeConsole {
  office:       string;
  office_label: string;
  rows:         OfficeConsoleRow[];
  load:         OfficeLoad[];
}

// --- Workflow analytics (IR-626, ADR-043) -----------------------------------

/** One party's active assignments now. Overdue counts only dated, running clocks. */
export interface AnalyticsOpenNow {
  party: string;
  open_count: number;
  /** Assignments in the office's pool, with nobody seated. */
  unseated: number;
  open_seats: number;
  /** No due date: opened before IR-619, or the party has no turnaround. */
  undated: number;
  /** Waiting on the owner: an open revision or document request. */
  paused: number;
  overdue: number;
  overdue_seats: number;
}

/** Elapsed time in stage. `record_type` null is the office's all-types row. */
export interface AnalyticsTimeInStage {
  party: string;
  record_type: string | null;
  records: number;
  turns: number;
  median_hours: number | null;
  p90_hours: number | null;
  /** The figures withheld because the cell has too few records. */
  too_few_for: ("median" | "p90")[];
}

export interface AnalyticsUnmeasured {
  party: string;
  started_before_log: number;
  ended_not_completed: number;
  still_open: number;
}

export interface AnalyticsThroughput {
  party: string;
  /** The Monday (Asia/Manila) the week starts on, YYYY-MM-DD. */
  week_start: string;
  entered: number;
  left: number;
}

export interface AnalyticsRevisionCycles {
  policy: string;
  cycles: number;
  cycles_preserving: number;
  preserved_clearances: number;
}

export interface WorkflowAnalytics {
  parties: { party: string; label: string }[];
  /** The earliest workflow event in scope; null when there is none yet. */
  data_since: string | null;
  generated_at: string;
  range: { from: string | null; to: string | null };
  thresholds: { median: number; p90: number };
  open_now: AnalyticsOpenNow[];
  time_in_stage: AnalyticsTimeInStage[];
  unmeasured: AnalyticsUnmeasured[];
  throughput: AnalyticsThroughput[];
  revision_cycles: AnalyticsRevisionCycles[];
  preserved_by_office: { party: string; policy: string; preserved_clearances: number }[];
}

export interface WorkflowAnalyticsQuery {
  office: string;
  from: string;
  to: string;
}
