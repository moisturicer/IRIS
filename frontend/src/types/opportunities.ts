/** ADR-050 decision 2. Grants, funding windows and internal calls are off the board. */
export type OpportunityType =
  | "conference"
  | "congress"
  | "symposium"
  | "workshop"
  | "journal"
  | "book_chapter";

/** ADR-050 decision 6 (IR-761): accepting through the paper deadline, then closed. */
export type CallPapersState = "accepting" | "closed";

/**
 * ADR-050 decisions 6 and 7 (IR-761). `over` begins the day after the event's
 * last date, so it can sit beside `accepting` while a later deadline keeps the
 * Call listed. A Call leaves the board list the day after its latest date.
 */
export type CallEventState = "upcoming" | "happening" | "over";

export interface Opportunity {
  id:               number;
  opportunity_type: OpportunityType;
  /** Server-rendered label for `opportunity_type`, e.g. "Book Chapter". */
  type_display:     string;
  title:            string;
  /** "About" on screen. */
  description:      string;
  /** "Link" on screen. Empty only on a Call migrated from a Conference Deadline. */
  external_url:     string;
  /** The paper deadline. */
  due_date:         string;
  /** Empty only on a Call migrated from a Conference Deadline. */
  location:         string;
  /** Classification ids (ADR-050 amendment 1). */
  areas:            number[];
  /** Their names, sorted, for display. */
  area_names:       string[];
  /** Always null on a Journal or Book Chapter, which has no event. */
  start_date:       string | null;
  end_date:         string | null;
  /** Free text: fees are often tiered or in another currency. */
  registration_fee: string;
  is_featured:      boolean;
  posted_by:        number | null;
  posted_by_name:   string;
  created_at:       string;
  updated_at:       string;
  /**
   * Both derived server-side, deliberately: computing the countdown in the
   * browser would drift with the viewer's clock and timezone, so two people
   * could see different numbers of days on the same deadline.
   */
  days_left:        number;
  is_closed:        boolean;
  /**
   * Two independent states, decided and worded server-side in Manila's date
   * (IR-761): a Call can be Accepting papers and Happening now at once. Show
   * the label as sent; branch on the state.
   */
  papers_state:     CallPapersState;
  /** "Accepting papers" or "Submissions closed". */
  papers_label:     string;
  /** Null for a Call with no event dates until it is Over. */
  event_state:      CallEventState | null;
  /**
   * "Upcoming", "Happening now", "Event over", or "Over" for a Call with no
   * event dates; null when `event_state` is.
   */
  event_label:      string | null;
  /**
   * May this viewer edit or delete it (IR-530)? Decided server-side by the
   * same permission class that guards the update and delete endpoints, so the
   * board never compares role names to decide whether to offer them.
   */
  can_edit:         boolean;
}

/** What a poster sends. Everything the server derives is left out. */
export interface OpportunityInput {
  opportunity_type: OpportunityType;
  title:            string;
  description:      string;
  external_url:     string;
  due_date:         string;
  location:         string;
  areas:            number[];
  start_date:       string | null;
  end_date:         string | null;
  registration_fee: string;
  is_featured:      boolean;
}

/** The whole board, every page of it, and whether this viewer may post. */
export interface OpportunityBoard {
  items:    Opportunity[];
  can_post: boolean;
}
