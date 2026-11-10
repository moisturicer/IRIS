import type { PipelineStatus } from "@/lib/constants";

export type ResearchOrigin = "unknown" | "institutional" | "imported_reference" | "synthetic";

export type IpType = "patent" | "copyright" | "trade_secret" | "utility_model" | "";

export const IP_TYPE_LABELS: Record<Exclude<IpType, "">, string> = {
  patent:        "Patent",
  copyright:     "Copyright",
  trade_secret:  "Trade Secret",
  utility_model: "Utility Model",
};

export interface RecordOwner {
  id:         number;
  user:       number;
  email:      string;
  full_name:  string;
  is_primary: boolean;
  /**
   * Draft IR-696: true only when this person's Profile can be opened from a
   * published paper's page. Absent or false means the name is plain text: a
   * suspended or former user's Profile answers 404, and a link there would land
   * on not-found. Never inferred from the id.
   */
  has_profile?: boolean;
}

export interface Author {
  id:   number;
  name: string;
  role: number | null;
}

export interface RecordListItem {
  origin?: ResearchOrigin;
  publication_year?: number | null;
  id:                    number;
  title:                 string;
  abstract:              string;
  year_accomplished:     number | null;
  /**
   * Absent, not null, when the record has no classification: the serializer's
   * `source="classification.name"` skips the field (found by IR-915's contract check).
   */
  classification_name?:  string | null;
  record_type_name:      string | null;
  pipeline_status:       PipelineStatus;
  is_ip:                 boolean;
  ip_type:               IpType;
  for_commercialization: boolean;
  community_extension:   boolean;
  access_count:          number;
  /** One-sentence hook generated with the AI Overview; null until one exists (IR-604). */
  ai_hook?:              string | null;
  /** Attachments on the record (documents.RecordUpload). */
  file_count:            number;
  /** Whether the authenticated manuscript reader can serve a PDF. */
  has_manuscript?:       boolean;
  created_at:            string;
  authors:               Author[];
}

/** The catalogue metadata kept with an unsent comparison (IR-574). */
export type ComparisonRecord = Pick<RecordListItem, "id" | "title" | "origin" | "classification_name">;

export interface DiscoverInterestOption { id: number; name: string }
export interface DiscoverInterests {
  classifications: DiscoverInterestOption[];
  psced: DiscoverInterestOption[];
}
export interface ForYouItem extends RecordListItem {
  reason: { kind: "selected_area" | "saved_area" | "latest"; area?: string };
}
export interface ForYouPage {
  mode: "for_you" | "latest";
  results: ForYouItem[];
  next_cursor: string | null;
  count: number;
}

/**
 * One row of `/records/mine/`: what a *My research* card shows, and nothing
 * else (IR-410, spec §4.9). Not Record detail -- the per-viewer review blocks
 * stay on Paper View, so the list costs the same queries for any length.
 */
export interface MyResearchItem {
  can_continue?:        boolean;
  id:                   number;
  title:                string;
  record_type_name:     string | null;
  authors:              Author[];
  adviser_name:         string | null;
  pipeline_status:      PipelineStatus;
  /** Derived by the server, as on Record detail; the client derives no stage. */
  workflow_state:       WorkflowState;
  workflow_state_label: string;
  /** Who has the record now, in tracker order; empty when nobody does. */
  holders:              { party: Party; label: string }[];
  /** Offices that have cleared it; `preserved` when kept through a resubmission (ADR-003). */
  cleared_offices:      { office: "itso" | "ierc" | "ktto"; label: string; preserved: boolean }[];
  submitter_status:     SubmitterStatus;
  created_at:           string;
  updated_at:           string;
}

/** One open request the owner must answer, worded by the server (IR-625). */
export interface WaitingItem {
  kind:         "revision" | "document";
  party:        Party;
  /** "Revision requested by IERC". */
  label:        string;
  /** The act that answers it: "Submit a new version". */
  action_label: string;
}

/**
 * Where an owner's record is, in the server's words (IR-625). `waiting_on_you`
 * is non-empty exactly when `workflow_state` is `awaiting_resubmission` or
 * `awaiting_document`. Carries no reviewer's name or words.
 */
export interface SubmitterStatus {
  /** "With your Adviser", "In specialist review: ITSO, IERC", … */
  line:           string;
  waiting_on_you: WaitingItem[];
}

/** One version as its owner reads its history: when it went in, and what each party decided. */
export interface SubmitterVersion {
  number:       number;
  cause_label:  string;
  submitted_at: string;
  decisions:    { party: Party; label: string; verdict: string; verdict_label: string }[];
}

export interface RecordReview {
  id:               number;
  stage:            string;
  status:           "approved" | "declined" | "rejected";
  comment:          string;
  reviewed_by_name: string | null;
  created_at:       string;
  /** The version it was made against; null for reviews written before IR-416. */
  version:          number | null;
}

export interface RecordClearance {
  office:           "itso" | "ierc" | "ktto";
  office_label:     string;
  status:           "pending" | "cleared" | "declined" | "rejected" | "not_cleared";
  /** Server-supplied wording, so a status can be renamed without a release. */
  status_label:     string;
  /**
   * The comment and who signed are review content: null to a viewer who may
   * not read the review (IR-479). The status is not.
   */
  comment:          string | null;
  reviewed_by_name: string | null;
  updated_at:       string;
  /**
   * True when this clearance survived a resubmission rather than being granted
   * again. Derived by the server (IR-139) -- the client used to compute it from
   * the last decline, which is a different rule than `resubmit_record` applies.
   */
  preserved:        boolean;
  /** What the latest version did to this clearance, with the version it applies to (IR-624). */
  carryover:         Carryover | null;
  carryover_version: number | null;
  /** "Cleared on v1, preserved", "Reset by v2": the server's words. */
  carryover_label:   string | null;
}

/**
 * Across the latest version (IR-624): `preserved` -- cleared on an earlier
 * version and kept -- or `reset` by it and awaiting review. The server's call
 * (`clearance_state.carryover`); the client never works either out.
 */
export type Carryover = "preserved" | "reset";

/** RDCO's later publish of an Unlisted paper (ADR-047 §10, IR-878). */
export interface TrackerPublishedLater {
  /** RDCO's party, in the server's words ("RDCO Final"). */
  label:             string;
  published_at:      string;
  published_by_name: string | null;
  note:              string | null;
}

/** What happened across resubmissions, and which offices survived them. */
export interface RecordResubmission {
  count:               number;
  last_resubmitted_at: string | null;
  /** Null when a sequential stage declined -- that path preserves nothing. */
  declining_office:    "itso" | "ierc" | "ktto" | null;
  offices_preserved:   Array<"itso" | "ierc" | "ktto">;
}

export interface RecordFileItem {
  id:         number;
  filename:   string;
  url:        string | null;
  size_bytes: number;
  created_at: string;
  /** The viewer may remove it: their office filed it and takes part (IR-476). */
  can_remove: boolean;
}

/** A public comment on a published paper (ADR-032 §7, IR-690). */
export interface PublicComment {
  id: number;
  author_name: string | null;
  body: string | null;
  created_at: string;
  edited_at: string | null;
  is_author: boolean;
  can_edit: boolean;
  can_report: boolean;
  reply_to: number | null;
  /** `writer` renders as [deleted], `moderator` as [removed]. */
  deletion_kind: "writer" | "moderator" | null;
}

/** The public thread and its count of comments that have not been deleted. */
export interface PublicCommentsResponse {
  comments: PublicComment[];
  count: number;
}

export type PublicCommentReportReason = "spam" | "harassment" | "off_topic" | "other";

/**
 * ADR-032 §10's action keys, as spec §4.8 lists them, with the two its
 * 2026-10-06 amendment adds (IR-411): `continue_draft`, reopening one's own
 * draft in Publish, and `attach_file`, an office filing a supplementary file
 * on a record it takes part in. IR-273 adds `replace_manuscript`: the owner
 * uploading a revised manuscript for the next version (ADR-032 §5 Amendment).
 * IR-270 adds the three Decisions: `accept_publish`, `keep_unlisted` (the
 * spec's `final_decide`, renamed to the act it grants) and `reject`. IR-271
 * adds `accept_proposal`, a Proposal's Adviser accepting it (the spec's
 * `decide_proposal`, which also named *Reject*; reject is `reject` on every
 * record). IR-508 adds the owner's three deletes, one per act, all served by
 * `DELETE /records/<id>/`: `delete_record` (a draft or rejected record, gone
 * now), `withdraw_submission` (in review, ending every open turn) and
 * `request_deletion` (accepted work, for RDCO to decide). Nothing renders them
 * yet. IR-797 adds RDCO's three acts on a paper in review, `replace_adviser`,
 * `add_owner` and `withdraw_paper`, which Paper View offers (IR-798).
 */
export type Capability =
  | "open_review"
  | "request_document"
  | "request_revision"
  | "withdraw_revision"
  | "route"
  | "send_to_rdco"
  | "accept_publish"
  | "accept_proposal"
  | "keep_unlisted"
  | "reject"
  | "office_review"
  | "add_reviewer"
  | "create_version"
  | "replace_manuscript"
  | "edit_details"
  | "continue_draft"
  | "delete_record"
  | "withdraw_submission"
  | "request_deletion"
  | "continue_as"
  | "set_embargo"
  | "release_embargo"
  | "release_ip"
  | "publish_unlisted"
  | "replace_adviser"
  | "add_owner"
  | "withdraw_paper"
  | "set_visibility"
  | "tag_ip"
  | "attach_file"
  | "comment_review"
  | "finish_review"
  | "comment_public"
  | "cite";

/**
 * `GET /records/<id>/metadata-suggestions/` (IR-406; spec §4.5). `pending`
 * while the manuscript is being read, `ready` once it has, `failed` when it
 * could not (an image-only scan included), `unsupported` when there is no
 * manuscript extraction at all. A `ready` field with nothing found is null.
 * `source` is `llamaextract` when LlamaExtract read a LlamaParse Manuscript
 * (IR-846), and `pdf_structure` when the stored structure was read.
 */
export interface MetadataSuggestions {
  state:       "pending" | "ready" | "failed" | "unsupported";
  /** The legacy projection, kept while clients move to `fields` (IR-833). */
  suggestions: { title: string | null; abstract: string | null };
  source:      "pdf_structure" | "llamaextract";
  /** Each field's value and where it was read, null when none was (IR-833). */
  fields?:     SuggestionFields;
  /** Opaque: the accepted manuscript these values were read from (IR-831). */
  manuscript_revision?: string | null;
  /** `queued`, `reading`, `retrying`, `ready`, `failed`, … (IR-831). */
  phase?:      string;
  /** A failed read the owner may ask to retry. */
  retryable?:  boolean;
  message?:    string | null;
}

/**
 * One value read from the PDF (IR-833). A LlamaExtract value (IR-846) also
 * carries the text it cites and the confidence LlamaExtract reported, which
 * the interface never shows as a number: only `low_confidence`, the server's
 * comparison with its threshold, becomes words ("Check this").
 */
export interface SuggestionEntry<T> {
  value:         T;
  source?:       "pdf_structure" | "llamaextract";
  basis:         "document_title" | "abstract_section" | "labelled_front_matter" | "cited_text";
  /** Only when the stored structure records them. */
  page:          number | null;
  region:        { page: number; left: number; top: number; right: number; bottom: number } | null;
  /** Publish may fill it in unasked: a title or abstract within its limit. */
  auto_apply:    boolean;
  /** Longer than the field allows: offered whole, for the author to shorten. */
  exceeds_limit: boolean;
  /** The text in the PDF the value was read from (IR-846). */
  matching_text?: string | null;
  /** As LlamaExtract reported it; absent when it reported none. Never shown. */
  confidence?:    number | null;
  /** Below the server's threshold: the author should check it. */
  low_confidence?: boolean;
}

export interface SuggestionFields {
  title:            SuggestionEntry<string> | null;
  abstract:         SuggestionEntry<string> | null;
  authors:          SuggestionEntry<string[]> | null;
  keywords:         SuggestionEntry<string[]> | null;
  publication_year: SuggestionEntry<number> | null;
}

/** The author's decision about a field Publish can fill in (IR-833). */
export interface FieldDecision {
  state:            "placeholder" | "automatic" | "accepted" | "authored" | "dismissed";
  source_revision?: string | null;
  /** What Undo restores, for an `automatic` value. */
  previous?:        string;
}

export type MetadataSources = Partial<Record<keyof SuggestionFields, FieldDecision>>;

/** Server-filtered fields: null means withheld or not recorded. */
export interface PaperPerson {
  id: number;
  name: string;
  role: string;
  office: string | null;
  college: string | null;
  department: string | null;
  program: string | null;
  email: string | null;
}

export interface PaperDueDate {
  party: Party;
  label: string;
  due_at: string | null;
  original_due_at: string | null;
  is_overdue: boolean;
  clock_paused: boolean;
}

export interface PaperDetails {
  /** Null when the viewer may not read every owner's registration affiliation. */
  colleges: string[] | null;
  programs: string[] | null;
  author_flags: { office: Party; label: string; hint: string }[];
  researchers: PaperPerson[];
  adviser: PaperPerson | null;
  /** Review content: null means not disclosed, not an empty review. */
  participants: PaperPerson[] | null;
  due_dates: PaperDueDate[] | null;
}

/**
 * Where a paper's embargo stands (ADR-052 §3, amended for IR-882). Every paper
 * starts `active`, with or without a date; a date never moves it, a release does.
 */
export type EmbargoState = "active" | "released";

export interface RecordEmbargo {
  state: EmbargoState;
  until: string | null;
  /** Set when the paper's text may already have gone out (embargo-set/). */
  notice?: string;
}

/** KTTO's release of an IP mark (ADR-052 §11). The mark itself stays. */
export interface RecordIpRelease {
  released:    boolean;
  released_at: string | null;
}

/** What `POST /records/<id>/ip-release/` answers. */
export interface IpReleaseResult {
  marked:   boolean;
  released: boolean;
}

export interface RecordDetail extends RecordListItem {
  /** Moved by each detail save; name it to make a save conditional (IR-833). */
  details_revision?: number | null;
  /** The owner's field-source decisions; null for anyone else (IR-833). */
  metadata_sources?: MetadataSources | null;
  /** Added in IR-686; absent only when using an older API. */
  paper_details?: PaperDetails;
  /** Null for anyone but the owners, the Adviser and office staff (ADR-052 §18). */
  embargo?: RecordEmbargo | null;
  /** Null for an unmarked paper, and to the same viewers as `embargo`. */
  ip_release?: RecordIpRelease | null;
  lineage?: {
    derived_from: { id: number; title: string; record_type_name: string | null } | null;
    continued_as: { id: number; title: string; record_type_name: string | null } | null;
  };
  /** Server-computed action offers (ADR-032 §10); every action re-checks authority. */
  capabilities:   Capability[];
  year_completed:  number | null;
  abstract:        string;
  abstract_file:   string | null;
  /**
   * These three are serialized with StringRelatedField, so the detail payload
   * carries the related object's display name — not its id. Use
   * `classification_name` / `record_type_name` for display.
   */
  classification:  string | null;
  psced:           string | null;
  record_type:     string | null;
  adviser:         number | null;
  /** The adviser's name, or their email when none is on file; null with no adviser (IR-472). */
  adviser_name:    string | null;
  /** Draft IR-696: whether the Adviser's Profile can be opened; see `RecordOwner.has_profile`. */
  adviser_has_profile?: boolean;
  added_by:        number | null;
  /** ADR-018: what the submitter requested; RDCO confirms at intake. */
  requires_ethics_review: boolean;
  requested_itso:  boolean;
  requested_ierc:  boolean;
  requested_ktto:  boolean;
  owners:          RecordOwner[];
  keywords?:       string[];
  is_deleted:      boolean;
  /** Null to a viewer who may not read the review: not disclosed, which is not none (IR-479). */
  reviews:         RecordReview[] | null;
  /** Per-office clearance state — makes clearance-aware resubmission visible. */
  clearances:      RecordClearance[];
  resubmission:    RecordResubmission;
  /** Server-worded stage. Never map a pipeline key to English on the client. */
  stage_label:     string;
  files:           RecordFileItem[];
  /**
   * Derived by the server from the routing tables, never stored (ADR-021 §4,
   * IR-258). A terminal record reports its stored status here instead.
   */
  workflow_state:       WorkflowState;
  workflow_state_label: string;
  current_holders:      TrackerHolder[];
  /**
   * The parties this viewer may ask the owner for documents as (ADR-022,
   * IR-262): a party they hold.
   */
  can_request_document: Party[];
  /**
   * The viewer's own reviewer seats on this record, withdrawn ones left out
   * (ADR-032 §4, IR-415). Never anyone else's.
   */
  my_seats:             ReviewerSeat[];
  /**
   * What stands between the viewer and their part of the review, in the
   * server's words (ADR-032 §10 Amendment, IR-681). Null when the viewer may
   * not read the review: not disclosed, which is not "nothing to say".
   */
  readiness?:           Readiness | null;
  /** The viewer's own download state; null when signed out, absent on older APIs (IR-677). */
  download?:            DownloadState | null;
  /** A server-offered claim from the viewer's office Pool; absent on older APIs. */
  review_claim?:        { assignment: number; label: string; party_label: string } | null;
  /**
   * ADR-032's `is_record_participant`: an owner, or anyone who has ever held
   * a seat here -- so a reviewer whose part is done keeps Review and Files.
   */
  is_participant:       boolean;
  /**
   * What the action bar may offer for routing (ADR-047 §1–§3): *Accept & send
   * to RDCO…* for the record's Adviser, and *Request review…* for an office
   * seat holder. A rendering hint; the endpoints re-check it.
   */
  routing:              RoutingFlags;
  /**
   * What the action bar may offer an office reviewer (IR-269): the office the
   * viewer may *Clear* or *Record finding* as, why not yet, and the office's
   * assignment for *Add reviewer*. A rendering hint; the endpoints re-check it.
   */
  office_review:        OfficeReviewFlags;
  /**
   * Revision requests (IR-272): whether the viewer may ask for one or
   * withdraw their party's, why nothing can be decided now, and every open
   * request for the owner's *Action required*. A rendering hint; the
   * endpoints re-check it.
   */
  revision:             RevisionFlags;
  /**
   * Decisions (IR-270): what the viewer may decide this record as -- the
   * Adviser's *Reject*, a Proposal Adviser's two, RDCO's three -- why not yet,
   * what deciding would close, and the token `decide/` checks so a stale
   * dialog never decides into a changed record. A rendering hint; the
   * endpoint re-checks it.
   */
  decision:             DecisionFlags;
  /**
   * RDCO's later publish of an Unlisted paper (ADR-047 §10, IR-878): what
   * holds it back -- its embargo -- or null. Null to everyone but an RDCO
   * member on an Unlisted paper. Optional: a fixture may leave it out.
   */
  publish_unlisted?:    { blocked: string | null } | null;
  /**
   * The record's versions, oldest first (ADR-032 §5, IR-416). Review
   * material: null to a viewer who may not read the review (IR-479), and
   * empty before the record is first submitted.
   */
  versions:             RecordVersion[] | null;
  /**
   * The manuscript is the owner's upload for a version not yet submitted
   * (IR-273). True for an owner only: everyone else is still served the
   * latest version's manuscript.
   */
  manuscript_unsubmitted: boolean;
  /** The owner's status, what waits on them, and each version's history. Null to anyone but an owner (IR-625). */
  submitter_status:     (SubmitterStatus & { history: SubmitterVersion[] }) | null;
}

/** One numbered snapshot of what the record put in front of its reviewers. */
export interface RecordVersion {
  number:          number;
  cause:           "submission" | "revision";
  cause_label:     string;
  created_at:      string;
  created_by_name: string | null;
  /** Null when this version was submitted with no manuscript. */
  manuscript_url:  string | null;
  /** What it was submitted with, one per upload slot (ADR-058 §2, IR-872). */
  documents?:               VersionDocument[];
  /** Uploads made while it was the latest version: "added during vN". */
  documents_added?:         VersionDocument[];
  /** True when `documents` is a best guess, for versions older than IR-872. */
  documents_reconstructed?: boolean;
  /** Its review text's state (ADR-058 §1 as amended, IR-871). Null with no manuscript. */
  review_text?:             VersionReviewText | null;
}

/** Whether a version's review text was read, and what to say if not (IR-871). */
export interface VersionReviewText {
  state:    "pending" | "read" | "no_text" | "unavailable" | "not_kept" | "not_read";
  /** Server-authored, e.g. "No text for v2, so it can't be compared." Null when read. */
  message:  string | null;
  warnings: { code: string; [detail: string]: unknown }[];
  /** `GET .../versions/<n>/text/` when read, else null. */
  url:      string | null;
}

/** One slot's file, as a version names it (IR-872). */
export interface VersionDocument {
  upload_id:    number;
  slot:         string;
  version:      number;
  uploaded_at:  string;
  download_url: string;
}

/**
 * What a Decision ends the review with (ADR-032 §2-§3; IR-270, IR-271):
 * `accept` on a Proposal only, `publish` / `keep_unlisted` on a Thesis or
 * Project, `reject` on either.
 */
export type DecisionOutcome = "accept" | "publish" | "keep_unlisted" | "reject";

export interface DecisionFlags {
  /** The party the viewer decides as, `adviser` or `rdco`; null for anyone else. */
  party:        Party | null;
  /** The outcomes on offer, in the bar's order; empty for anyone who may not decide. */
  outcomes:     DecisionOutcome[];
  /** Why the decision cannot be taken yet: an unopened seat, an open revision request. */
  blocked:      string | null;
  /** What deciding now would close; null for anyone who may not decide. */
  closes:       DecisionCloses | null;
  /** An outcome held back while the rest are not: a Proposal's Accept, by the Adviser's own Must fix (IR-874). */
  blocked_outcomes?: Partial<Record<DecisionOutcome, string>>;
  /** Deciding now closes an open Must fix, so the comment is required as its reason. */
  reason_required?:  boolean;
  /** Echoed to `decide/`: a record that moved since is refused with a 409. */
  token:        string | null;
  /** The author's flags, shown in the Adviser's *Accept & send to RDCO* dialog. */
  author_hints: string[];
  /** For RDCO only: while it is `active` RDCO can't publish, only keep unlisted or reject (ADR-052 §14). */
  embargo?:     RecordEmbargo | null;
}

export interface DecisionCloses {
  /** Each review a decision would end, with whoever is reviewing there now. */
  assignments:       { party: Party; label: string; holders: string[] }[];
  /** How many open document requests it would withdraw. */
  document_requests: number;
  revision_requests?: { id: number; party: Party; label: string; reason: string }[];
  findings?: { party: Party; label: string; comment: string }[];
  /** The open threads deciding closes, the decider's own drafts included (IR-874). */
  threads?: { id: number; party: Party | null; label: string; severity: ThreadSeverity | null; anchored: boolean }[];
}

export interface OfficeReviewFlags {
  /** The specialist office the viewer holds an open seat for, or null. */
  party:      Party | null;
  label:      string | null;
  /** Why the act cannot be taken yet (an unopened seat, an open document request). */
  blocked:    string | null;
  /** Why *Clear* alone is held: the office's own open Must fix threads (IR-874). */
  clear_blocked?: string | null;
  assignment: number | null;
}

export interface RevisionFlags {
  /** The party the viewer holds an open seat for, and may ask as; null otherwise. */
  party:            Party | null;
  label:            string | null;
  /** Why the viewer cannot ask yet: their seat is not opened. */
  blocked:          string | null;
  /** Their party's open request, which they may withdraw instead: a party asks once. */
  withdrawable:     number | null;
  /** Why nobody may decide the record now: a revision request is open (ADR-032 §11). */
  decision_blocked: string | null;
  /** Every open request, oldest first. */
  open:             OpenRevisionRequest[];
  /**
   * For an owner, the version that would answer the open requests (IR-273);
   * null for anyone else, or with none open.
   */
  new_version:      NewVersionHint | null;
}

/** What submitting a new version would do, for its confirmation (IR-273). */
/** Where a thread's passage is in one later Version (ADR-032 §7, IR-876). */
export interface ThreadPlace {
  version:         number;
  outcome:         "found" | "changed" | "removed";
  /** Null when the passage was removed. */
  page:            number | null;
  /** The quote when found, the edited passage when changed. */
  text:            string;
  regions:         PageRegion[];
  /** The page the suggested wording appears on in this Version, or null. */
  suggestion_page: number | null;
}

/** One thread in the response to reviewers (ADR-032 §7, IR-876). */
export interface ResponseLetterEntry {
  thread:      number;
  party:       string;
  party_label: string;
  severity:    ThreadSeverity | null;
  comment:     string;
  version:     number | null;
  page:        number | null;
  quote:       string;
  /** Null: no answer given. */
  answer:      ThreadAnswerPayload["kind"] | null;
  note:        string;
}

/** The response a Version was submitted with, frozen then. */
export interface ResponseLetter {
  version:    number;
  created_at: string;
  entries:    ResponseLetterEntry[];
}

export interface NewVersionHint {
  /** The version it would be. */
  number:   number;
  /** The parties that asked, who review it. */
  rereview: string[];
  /** The offices whose clearance it keeps; empty under the restart-all policy. */
  kept:     string[];
  /** Why it cannot be submitted yet: nothing changed, or a Must fix has no answer. */
  blocked:  string | null;
  /** The response to reviewers it would carry, as it stands (IR-876). */
  letter?:  ResponseLetterEntry[];
}

export interface OpenRevisionRequest {
  id:           number;
  party:        Party;
  label:        string;
  /** Plain text. Null, as `requested_by` is, to a viewer who may not read the review (IR-479). */
  reason:       string | null;
  requested_by: string | null;
  /** The version it was made against; null for one made before versions were recorded. */
  version:      number | null;
  created_at:   string;
}

/** An office reviewer's two outcomes (ADR-032 §3): offices never reject or publish. */
export type OfficeReviewOutcome = "cleared" | "finding";

/** `GET /assignments/<id>/add-reviewer/`: the office's members, marked when already seated. */
export interface AddReviewerOptions {
  assignment:  number;
  party:       Party;
  party_label: string;
  members:     { id: number; name: string; seated: boolean }[];
}

export interface RoutingFlags {
  send_to_rdco: boolean;
  /** Why *Accept & send to RDCO* is held: the Adviser's own open Must fix threads (IR-874). */
  send_to_rdco_blocked?: string | null;
  route_as:         Party | null;
  /**
   * Where onward *Route* may send this record, as the server's party graph
   * has it (IR-685): *Request review* lists exactly these. Empty when the
   * viewer cannot route.
   */
  targets:          { party: Party; label: string }[];
}

/** One office the routing dialog offers (`GET /records/<id>/route-options/`). */
export interface RouteTarget {
  party:         Party;
  label:         string;
  /** Who may be nominated there: the office's members. */
  members:       { id: number; name: string }[];
  /** The office already reviews this record: routing there only adds a nominee. */
  already_holds: boolean;
  /** The author's ADR-018 flag for this office, worded; routes nothing by itself. */
  author_hint:   string | null;
}

export interface RouteOptions {
  from_party: Party;
  from_label: string;
  /** True for the Adviser's *Accept & send to RDCO*, false for onward routing. */
  accept:     boolean;
  targets:    RouteTarget[];
  suggested_offices?: string[];
}

/** A routing request: one reason for the decision, zero or several nominees per office. */
export interface RouteRequest {
  to:     { party: Party; nominees?: number[] }[];
  suggested_offices?: string[];
  reason: string;
}

// ---------------------------------------------------------------------------
// Reviewer seats (ADR-032 §4, IR-415)
// ---------------------------------------------------------------------------

export type SeatState = "assigned" | "in_review" | "done" | "withdrawn";
export type SeatSource = "entry" | "claimed" | "assigned" | "nominated" | "added";

/** The states in which a seat is still held: not finished, not taken away. The server's `OPEN_SEAT_STATES`. */
export const OPEN_SEAT_STATES: readonly SeatState[] = ["assigned", "in_review"];

/** One person reviewing a record for a party. Every seat endpoint answers with this. */
export type ReadinessVerdict = "ready" | "blocked" | "waiting_on_you" | "none";

/** One fact in Readiness. The browser renders `label` and never words its own. */
export interface ReadinessItem {
  kind:       string;
  severity:   "blocker" | "info";
  label:      string;
  party:      string | null;
  actor_name: string | null;
  since:      string | null;
  /** Due dates only; null on every other item. */
  paused:     boolean | null;
  action:     { kind: string; target: string | null } | null;
}

export interface Readiness {
  verdict:  ReadinessVerdict;
  headline: string;
  items:    ReadinessItem[];
}

export interface ReviewerSeat {
  id:            number;
  assignment:    number;
  record:        number;
  party:         Party;
  party_label:   string;
  reviewer:      number | null;
  reviewer_name: string | null;
  state:         SeatState;
  state_label:   string;
  /** The viewer's own recorded verdict in the server's words; on my_seats. */
  verdict_label?: string | null;
  source:        SeatSource;
  assigned_by:   number | null;
  assigned_at:   string | null;
  /** Stamped by *Open review*: when this reviewer started. */
  opened_at:     string | null;
  done_at:       string | null;
}

// ---------------------------------------------------------------------------
// Review & Routing Tracker (IR-258, ADR-021 §14)
// ---------------------------------------------------------------------------

/**
 * ADR-021 §1. `intake` is retired (ADR-032 §13): it survives only on history
 * the server sends -- an old assignment, review or request -- and is never
 * assigned, routed to or staffed.
 */
export type Party = "intake" | "adviser" | "itso" | "ierc" | "ktto" | "rdco";

export type WorkflowState =
  | "awaiting_resubmission"
  | "awaiting_document"
  | "submitted"
  | "final_review"
  | "in_review"
  | PipelineStatus;

export type TrackerPartyState =
  | "active"
  | "completed"
  | "withdrawn"
  | "not_requested"
  | "awaiting"
  /** RDCO on a new-model record no specialist office has held (ADR-032 §10, IR-269). */
  | "not_required";

/**
 * What a finished (or reviewing) party concluded: its clearance status for an
 * office, else its latest review decision. Named so an outcome the UI has not
 * styled fails `tsc` rather than falling through.
 */
export type TrackerOutcome =
  | RecordClearance["status"]
  | "approved"
  | "rejected"
  | "negative_finding";

export interface TrackerReview {
  id:               number;
  party:            Party | null;
  label:            string | null;
  status:           string;
  status_label:     string;
  comment:          string;
  reviewed_by_name: string | null;
  created_at:       string | null;
  /** The version it was made against; null for reviews written before IR-416. */
  version:          number | null;
}

/** Someone a review comment mentions, or may mention (IR-877). */
export interface MentionedPerson {
  id:   number;
  name: string;
}

/**
 * One message in a record's review discussion (ADR-032 §7, IR-419). Private
 * to the review; public discussion is a separate model.
 */
export interface ReviewComment {
  id:          number;
  author:      number | null;
  author_name: string | null;
  /** Plain text, verbatim. Never render as markup. */
  body:        string;
  /** The version it was made against; null on a record with no version yet. */
  version:     number | null;
  /** The top-level comment this one answers. Threads are one level deep. */
  reply_to:    number | null;
  created_at:  string;
  /** Set once an edit changed the body. */
  edited_at:   string | null;
  /** The server's answer: Edit is offered only where this is true. */
  can_edit:    boolean;
  /** The people it mentions (IR-877). Optional so an older payload still reads. */
  mentions?:   MentionedPerson[];
  /*
   * The thread (ADR-032 §7, 2026-11-04; IR-874). A top-level comment is a
   * thread; a reply carries these empty. Optional so an older payload or a
   * fixture without them still reads as a plain comment.
   */
  /** The party it belongs to; null for the authors' own threads. */
  party?:                ThreadParty | null;
  /** Server-worded party: "The authors", "Adviser", "ITSO"... */
  party_label?:          string | null;
  /** A reviewer's thread only; null on an owner's thread and on a reply. */
  severity?:             ThreadSeverity | null;
  /** Unsent: seen only by its writer until *Finish review* sends it. */
  is_draft?:             boolean;
  /** The finished review that sent it, or null. */
  round?:                number | null;
  /** The passage it is about; null for a general thread. */
  anchor?:               ThreadAnchor | null;
  state?:                ThreadState | null;
  resolved_by?:          string | null;
  resolved_at?:          string | null;
  closed_by_decision?:   number | null;
  /** The Decision's comment, the reason it closed. */
  closed_reason?:        string | null;
  answer?:               ThreadAnswerPayload | null;
  /** A reviewer's replacement text for the passage; empty for none (IR-876). */
  suggestion?:           string;
  /** Where the passage is in the newest Version it was looked for in, or null. */
  place?:                ThreadPlace | null;
  /** The Version from which the thread is Outdated, or null (IR-876). */
  outdated_since?:       number | null;
  /**
   * Accepted wording looked for in the first Version placed after it was
   * accepted: its page there, or a null page when it isn't. Null until
   * such a Version exists (IR-876).
   */
  wording_check?:        { version: number; page: number | null } | null;
  /**
   * Why an open thread's passage hasn't been followed into the next Version,
   * such as a Version with no text, or null when there is nothing to explain
   * (IR-1009).
   */
  not_followed?:         { version: number; message: string } | null;
  /** Severity changes, resolving and reopening, oldest first. Empty on a draft. */
  events?:               ThreadEvent[];
  /*
   * The server's answers. Every thread control is offered exactly where its
   * flag is true; the screen compares no role (ADR-032 §10).
   */
  can_delete?:           boolean;
  can_change_severity?:  boolean;
  can_resolve?:          boolean;
  can_reopen?:           boolean;
  can_answer?:           boolean;
}

/** A thread's party: an office, the Adviser, or (null) the authors. */
export type ThreadParty = Party;

/** How much a reviewer's thread asks (ADR-032 §7). A Suggestion never blocks. */
export type ThreadSeverity = "must_fix" | "suggestion";

/** `closed`: a Decision ended the review with the thread still open. */
export type ThreadState = "open" | "resolved" | "closed";

/** ADR-031's page-fraction rectangle, the same shape a citation's region has. */
export interface PageRegion {
  page:   number;
  left:   number;
  top:    number;
  right:  number;
  bottom: number;
}

/**
 * Two Versions compared (ADR-058 §3 as amended 2026-11-08, IR-873):
 * `GET /records/<id>/versions/compare/`. Both sides are read by one reader,
 * and no field names it. Only `ready` carries the comparison itself.
 */
export type ComparisonState = "ready" | "preparing" | "unavailable" | "no_text";
export type ChangeKind = "changed" | "added" | "removed" | "moved";

/** One side of a change: the passage, its section key and where it is. */
export interface ChangeSide {
  section: string;
  text:    string;
  page:    number;
  regions: PageRegion[];
}

export interface VersionChange {
  kind:      ChangeKind;
  /** `tentative`: possibly text the reader missed, not an edit. */
  certainty: "established" | "tentative";
  from:      ChangeSide | null;
  to:        ChangeSide | null;
  /** A changed passage's words, in order, the differing ones marked. */
  words?:    { op: "equal" | "delete" | "insert"; text: string }[];
}

export interface SectionHeading {
  key:     string;
  heading: string;
  page:    number | null;
}

export interface ChangeCounts {
  changed: number;
  added:   number;
  removed: number;
  moved:   number;
}

export interface SectionComparison {
  status:  "unchanged" | "changed" | "added" | "removed";
  renamed: boolean;
  moved:   boolean;
  from:    SectionHeading | null;
  to:      SectionHeading | null;
  changes: VersionChange[];
  counts:  ChangeCounts;
  /** The viewer ticked this section's text as viewed (IR-877); theirs alone. */
  viewed?: boolean;
}

export interface ComparisonNotice {
  code:    "sections_unidentified" | "may_be_unreliable";
  side:    "from" | "to";
  message: string;
}

export interface DocumentComparison {
  slot:   string;
  status: "unchanged" | "replaced" | "added" | "removed";
  from:   number | null;
  to:     number | null;
}

/** A sent thread on either Version, placed under a section (or null, by page). */
export interface PlacedThread {
  thread:  number;
  side:    "from" | "to";
  page:    number | null;
  section: number | null;
}

export interface VersionComparisonPayload {
  state:     ComparisonState;
  /** What to tell the reviewer; null when ready. */
  message:   string | null;
  from:      number;
  to:        number;
  documents: DocumentComparison[];
  mode?:     "sections" | "pages";
  sections?: SectionComparison[];
  /** By page: every change, in order. */
  changes?:  VersionChange[];
  notices?:  ComparisonNotice[];
  counts?:   ChangeCounts & { sections_renamed: number; sections_moved: number };
  threads?:  PlacedThread[];
}

/** A passage of one Version: where an anchored thread points. */
export interface ThreadAnchor {
  version:  number;
  page:     number;
  quote:    string;
  prefix?:  string;
  suffix?:  string;
  regions?: PageRegion[];
}

/** The owner's answer to a reviewer's thread. Neither answer resolves it. */
export interface ThreadAnswerPayload {
  kind: "addressed" | "declined";
  note: string;
  by:   string | null;
  at:   string | null;
}

export interface ThreadEvent {
  kind:       "severity_changed" | "resolved" | "reopened" | "answered" | "closed_by_decision";
  actor_name: string | null;
  from:       string | null;
  to:         string | null;
  at:         string;
}

/** What `finish-review/` finishes a review with (ADR-032 §7). */
export type ReviewVerdict =
  | "comment_only"
  | "request_revision"
  | "send_to_rdco"
  | "cleared"
  | "finding"
  | "accept"
  | "publish"
  | "keep_unlisted"
  | "reject";

/** `POST /records/<id>/finish-review/`. */
export interface FinishReviewRequest {
  verdict:            ReviewVerdict;
  summary:            string;
  to?:                RouteRequest["to"];
  suggested_offices?: string[];
  token?:             string;
}

/** One finished review, on the tracker (IR-874). Review content. */
export interface ReviewRound {
  id:         number;
  party:      Party;
  label:      string;
  actor_name: string | null;
  version:    number | null;
  verdict:    ReviewVerdict;
  summary:    string;
  review:     number | null;
  /** How many threads it sent. */
  threads:    number;
  created_at: string;
}

export interface TrackerHolder {
  party:     Party;
  label:     string;
  opened_at: string | null;
  opened_by: string | null;
}

export interface TrackerPartyRow extends AssignmentDeadline {
  party:         Party;
  /** Server-worded; Intake reads differently to staff and to students. */
  label:         string;
  state:         TrackerPartyState;
  state_label:   string;
  /**
   * Only for an active party: true once it has recorded a review, false while
   * it is requested but not yet started. Always false in any other state.
   */
  started:       boolean;
  /** Null for a party that was never assigned. */
  outcome:       TrackerOutcome | null;
  outcome_label: string | null;
  at:            string | null;
  preserved:     boolean;
  /** As on `RecordClearance`; null for a party that holds no clearance (IR-624). */
  carryover:         Carryover | null;
  carryover_version: number | null;
  carryover_label:   string | null;
  /**
   * This party has an open document request and is waiting on it (◐). Null
   * when the viewer may not read the record's document requests (IR-349):
   * not disclosed, which is not the same as false.
   */
  awaiting_document: boolean | null;
  /**
   * The outcome is an earlier review round's, standing while the office
   * reviews again; `outcome_label` already says so (IR-269).
   */
  outcome_earlier: boolean;
  /** Active, with nobody there reviewing it yet: the office's pool (◌). */
  in_pool:         boolean;
  /** This party has an open revision request: *Changes requested* (IR-272). */
  changes_requested: boolean;
  /**
   * The Decision that withdrew this party's unfinished work, worded by the
   * server ("RDCO published the record"); null otherwise (IR-270).
   */
  withdrawn_by_decision?: string | null;
  /**
   * Who is reviewing for this party, per seat. Null when the viewer does not
   * take part in the review: not disclosed, which is not the same as none.
   */
  seats:           TrackerSeat[] | null;
}

/**
 * The party's turnaround clock (IR-619; `docs/testing/ASSIGNMENT_DEADLINES.md`),
 * spread onto each tracker party row. All null and false for a party with no
 * assignment, or none configured.
 */
export interface AssignmentDeadline {
  due_at:          string | null;
  /** The current version's original deadline, before any extension. */
  original_due_at: string | null;
  /** Never for a paused clock or a closed assignment: the server's call. */
  is_overdue:      boolean;
  /** Waiting on the owner: an open document request or revision. */
  clock_paused:    boolean;
  can_extend:      boolean;
  extensions:      AssignmentExtension[];
}

export interface AssignmentExtension {
  id:              number;
  previous_due_at: string;
  due_at:          string;
  /** Null to a viewer who may not read the review. */
  reason:          string | null;
  system:          boolean;
  actor:           number | null;
  created_at:      string;
}

export interface TrackerSeat {
  /** Stable identity for a server-projected profile card (IR-686). */
  reviewer?: number | null;
  reviewer_name: string | null;
  state:         SeatState;
  state_label:   string;
  /** A finished seat's own verdict: `approved` (cleared) or `negative_finding`. */
  verdict:       string | null;
  verdict_label: string | null;
}

export interface TrackerRoutingGroup {
  group_id:   string;
  /** Null when the submitter sent the record in. */
  from:       Party | null;
  from_label: string | null;
  to:         Party[];
  to_labels:  string[];
  /** Who routed it, and why: null to a viewer who may not read the review (IR-479). */
  actor:      string | null;
  reason:     string | null;
  at:         string | null;
}

export interface TrackerResubmission {
  withdrawn_by_decision?: string | null;
  id:           number;
  party:        Party;
  label:        string;
  state:        "open" | "resubmitted" | "withdrawn";
  state_label:  string;
  /** Null, as `requested_by` and `resolved_by` are, to a viewer who may not read the review (IR-479). */
  reason:       string | null;
  /** The `declined` review that made this request, one of `reviews` (IR-412). */
  review:       number;
  /** The version it was made against; null for one made before versions were recorded (IR-272). */
  version:      number | null;
  requested_by: string | null;
  created_at:   string | null;
  resolved_at:  string | null;
  /** Who resubmitted, or withdrew, and so closed it (IR-412). */
  resolved_by:  string | null;
}

/**
 * A seat a coordinator moved to another member (IR-623). The names and the
 * reason are null to a viewer who may not read the review (IR-479).
 */
export interface TrackerReassignment {
  seat:      number;
  party:     Party;
  label:     string;
  from_name: string | null;
  to_name:   string | null;
  by_name:   string | null;
  reason:    string | null;
  at:        string | null;
}

/** One movement of an assignment's due date (ADR-043 §6): by a coordinator, or by a document pause. */
export interface DeadlineExtension {
  id:              number;
  previous_due_at: string;
  due_at:          string;
  /** Null, as `actor` is, to a viewer who may not read the review. */
  reason:          string | null;
  /** Moved by IRIS itself, for a document-request pause; no person did it. */
  system:          boolean;
  actor:           number | null;
  actor_name:      string | null;
  created_at:      string;
}

/** An assignment's due-date history on the tracker. Only what the timeline reads is typed. */
export interface TrackerDeadlineHistory {
  assignment: number;
  party:      Party;
  label:      string;
  extensions: DeadlineExtension[];
}

export interface RecordTracker {
  record_id:             number;
  record_type:           string | null;
  workflow_state:        WorkflowState;
  workflow_state_label:  string;
  current_holders:       TrackerHolder[];
  parties:               TrackerPartyRow[];
  routing_history:       TrackerRoutingGroup[];
  /** Routing was not recorded before this date (IR-257's backfill wrote none). */
  routing_recorded_from: string | null;
  /**
   * Null to a viewer who may not read the review (IR-479): who reviewed and
   * what they wrote is internal workflow data, as document requests are.
   */
  reviews:               TrackerReview[] | null;
  /** Each a timeline entry of its own (IR-416). Null as `reviews` is. */
  versions:              RecordVersion[] | null;
  /** The review discussion, oldest first (IR-419). Null as `reviews` is. */
  review_comments:       ReviewComment[] | null;
  /** Each finished review, oldest first (IR-874). Null as `reviews` is; absent on older APIs. */
  review_rounds?:        ReviewRound[] | null;
  resubmissions:         TrackerResubmission[];
  /**
   * RDCO published the paper from Unlisted after its Decision (IR-878), or
   * null. Who and the note are null to a viewer who may not read the review.
   * Optional: a fixture may leave it out.
   */
  published_later?:      TrackerPublishedLater | null;
  /** Null when the viewer may not read them (IR-349) -- not "there are none". */
  document_requests:     DocumentRequest[] | null;
  clearances:            RecordClearance[];
  resubmission:          RecordResubmission;
  /** Coordinators' reassignments (IR-623). Optional: a fixture may leave it out. */
  reassignments?:               TrackerReassignment[];
  /** Every assignment's due date and its extensions (ADR-043, IR-619). */
  assignment_deadline_history?: TrackerDeadlineHistory[];
}

export interface RecordFormData {
  origin?: ResearchOrigin;
  publication_year?: number | null;
  keywords?:             string[];
  owner_emails?:         string[];
  title:                 string;
  year_accomplished?:    number;
  year_completed?:       number;
  abstract?:             string;
  classification?:       number | null;
  psced?:                number | null;
  record_type?:          number;
  adviser?:              number;
  is_ip?:                boolean;
  for_commercialization?: boolean;
  community_extension?:  boolean;
  /** ADR-018: conditional parallel-office routing. */
  requires_ethics_review?: boolean;
  requested_itso?:        boolean;
  requested_ierc?:        boolean;
  requested_ktto?:        boolean;
  /** Flat list of author name strings — backend creates Author rows. */
  authors?:              string[];
  metadata_sources?:     MetadataSources;
  /** The revision last seen; a newer one on the server refuses the save (409). */
  expected_details_revision?: number;
}

export interface Classification {
  id:   number;
  name: string;
}

export interface PSCEDClassification {
  id:   number;
  name: string;
}

export interface RecordType {
  id:   number;
  name: string;
}

/**
 * Where the viewer's own download of a record stands (IR-677, ADR-048), in
 * the server's words. The page picks its control from `state` and never
 * decides access itself; the download route re-checks everything.
 */
export interface DownloadState {
  state:            "exempt" | "granted" | "none" | "pending" | "declined" | "revoked" | "expired";
  allowed:          boolean;
  /** Server-authored sentence explaining the state. */
  message:          string;
  /** When a live grant ends; null unless `state` is "granted". */
  grant_expires_at: string | null;
  /** The viewer's own request this state comes from, if any. */
  request:          number | null;
  /**
   * RDCO's note when `state` is "declined" or "revoked" (IR-688); "" otherwise,
   * and on a decline made before notes existed ("No note recorded").
   */
  rdco_note?:       string;
}

export interface DownloadRequest {
  id:                  number;
  record:              number;
  record_title:        string;
  requested_by:        number;
  requested_by_name:   string | null;
  requested_by_email:  string | null;
  /** Why the reader asks (IR-688). Blank only on requests made before notes. */
  note:                string;
  status:              "pending" | "approved" | "declined" | "revoked" | "cancelled";
  /** RDCO's reason for a decline or a revocation; "" otherwise. */
  rdco_note:           string;
  reviewed_by:         number | null;
  reviewed_at:         string | null;
  grant_expires_at:    string | null;
  /** Approved and unexpired: RDCO may still revoke it. Worked out by the server. */
  grant_live:          boolean;
  revoked_at:          string | null;
  cancelled_at:        string | null;
  created_at:          string;
}

/**
 * One of the reader's own download requests, for My Library (IR-743). The
 * server works out `state` and `actions`, so the browser decides no access.
 */
export interface ReaderDownloadRequest {
  id:               number;
  record:           number;
  record_title:     string;
  /** Why the reader asked. Blank only on requests made before notes. */
  note:             string;
  created_at:       string;
  state:            "pending" | "granted" | "declined" | "revoked" | "expired";
  /** When a live grant ends; null unless `state` is "granted". */
  grant_expires_at: string | null;
  /** RDCO's reason when declined or revoked; "" otherwise, or when none was recorded. */
  rdco_note:        string;
  /** What this row offers. Only a record's newest request offers anything. */
  actions:          ("cancel" | "download" | "request_again")[];
}

export interface DeleteRequest {
  id:                  number;
  record:              number;
  record_title:        string;
  requested_by:        number;
  requested_by_name:   string | null;
  requested_by_email:  string | null;
  reason:              string;
  status:              "pending" | "approved" | "declined";
  reviewed_by:         number | null;
  reviewed_at:         string | null;
  created_at:          string;
}

// ---------------------------------------------------------------------------
// Document requests (ADR-022, IR-262)
// ---------------------------------------------------------------------------

export type DocumentRequestState = "open" | "fulfilled" | "withdrawn";
export type DocumentRequestItemState = "missing" | "uploaded" | "accepted" | "rejected";

export interface DocumentRequestItem {
  id:          number;
  /** Null for a free-text "Other" item. */
  slot:        number | null;
  label:       string;
  state:       DocumentRequestItemState;
  state_label: string;
  upload:      number | null;
  uploaded_at: string | null;
  /**
   * The requesting party's reason, the last time it rejected an upload
   * (IR-263). A rejected item is back to `missing`; this says why. Plain
   * text. Null when it was never rejected.
   */
  rejection_reason: string | null;
  /** When the requesting party last accepted or rejected an upload. */
  decided_at:  string | null;
}

export interface DocumentRequest {
  id:           number;
  party:        Party;
  /** Server-worded; Intake reads "Intake" to the owner. */
  label:        string;
  state:        DocumentRequestState;
  state_label:  string;
  /** Plain text, as the reviewer wrote it. Never render as markup. */
  message:      string;
  requested_by: string | null;
  created_at:   string;
  closed_at:    string | null;
  /**
   * The viewer can staff the party that asked, so may accept, reject or
   * withdraw (ADR-022 §3.4, §4). Server-decided; the controls follow it.
   */
  can_manage:   boolean;
  items:        DocumentRequestItem[];
}

/** `PATCH /document-request-items/<id>/` (IR-263). A rejection needs a reason. */
export type DocumentRequestItemDecision =
  | { action: "accept" }
  | { action: "reject"; reason: string };

/** One entry of a new request: a picklist slot, or free text for "Other". */
export type DocumentRequestItemInput = { slot: number } | { label: string };

export interface DocumentRequestSlot {
  id:   number;
  name: string;
}
