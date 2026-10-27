export type OpportunityType =
  | "internal_call"
  | "conference_deadline"
  | "funding_window"
  | "institutional_grant";

export type OpportunitySource = "internal" | "external";

export interface Opportunity {
  id:               number;
  opportunity_type: OpportunityType;
  /** Server-rendered label for `opportunity_type`, e.g. "Funding Window". */
  type_display:     string;
  title:            string;
  posting_office:   string;
  audience:         string;
  description:      string;
  /** Decimal string from DRF, or null — a conference deadline has no ceiling. */
  funding_ceiling:  string | null;
  external_url:     string;
  due_date:         string;
  is_featured:      boolean;
  tags:             string[];
  source:           OpportunitySource;
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
  posting_office:   string;
  audience:         string;
  description:      string;
  funding_ceiling:  string | null;
  external_url:     string;
  due_date:         string;
  is_featured:      boolean;
  tags:             string[];
  source:           OpportunitySource;
}

/** The whole board, every page of it, and whether this viewer may post. */
export interface OpportunityBoard {
  items:    Opportunity[];
  can_post: boolean;
}
