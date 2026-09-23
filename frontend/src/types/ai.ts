/**
 * A quoted span of a Record's text, carrying the page it came from (IR-284).
 *
 * The reader-facing counterpart of a chunk — see `CONTEXT.md`. A chunk is how
 * IRIS divides a document for retrieval; a Passage is what a citation shows a
 * person, which is why this type says `page` and `text` rather than
 * `source_page` and `content`.
 */
export interface Passage {
  chunk_id:      number;
  record_id:     number;
  record_title:  string;
  /** The page in the source PDF. Null when extraction could not place it. */
  page:          number | null;
  /** The quoted text itself, as the paper words it. */
  text:          string;
  /** The section trail the passage sits under, outermost first. */
  context_path:  string[];
  score:         number;
}

/**
 * A Passage an answer cited, with the marker it was cited by.
 *
 * `marker` is how "[2]" in the answer text maps to the quote supporting it,
 * and it carries no score: a citation is what the model used, not what ranked
 * well, and a relevance number beside a quote reads as confidence in the claim.
 */
export type Citation = Omit<Passage, "score"> & { marker: number };

/** A Record card: whose work a Passage came from, for the card the UI renders. */
export interface SemanticSearchResult {
  id:             number;
  title:          string;
  abstract:       string;
  authors:        string;          // comma-separated display string
  year:           number | null;
  classification: string | null;
  /**
   * How well this record matched, on whichever path produced it: the best of its
   * passages' scores from an answer or a search, or the record's own cosine
   * similarity from related works. Cosine similarity is signed — 1 is the same
   * direction, 0 unrelated, negative opposed. Comparable within one response,
   * not across them.
   */
  score:          number;
}

/**
 * What the ask endpoint actually did — surfaced so the UI never implies more than ran.
 *
 * `extractive` is gone as of IR-283. There is no longer a path that composes an
 * answer out of the sources: when no model is reachable the answer is replaced
 * by an explicit `unavailable` state and the sources are returned unsummarised,
 * which is what ADR-008 asks for.
 */
export type AIAnswerMode = "generative" | "no_results" | "unavailable";

/** The index answers are ranked against. Null before anything has been indexed. */
export interface EmbeddingSpaceInfo {
  id:          number;
  model_id:    string;
  dimensions:  number;
  metric:      string;
}

export interface AIStatus {
  embedding_space:  EmbeddingSpaceInfo | null;
  generative:       boolean;
  /** Records with indexed passages that the asker may read. */
  indexed_records:  number;
  /**
   * True while ADR-015's disclosure gate is bypassed for development
   * (IR-317). Answers are being produced over content that no embargo check
   * cleared, so the interface says so rather than letting a screenshot look
   * like a shipped configuration. Removed with the bypass, by IR-250.
   */
  disclosure_bypass: boolean;
}

export interface AIAnswer {
  /** Answer text, or null when nothing in the corpus matched. */
  answer:    string | null;
  /**
   * The Passages the answer cited, in marker order. Always readable by the
   * asker — retrieval never returns a passage from a Record they may not open.
   */
  citations: Citation[];
  /** The retrieved records themselves, so the UI need not re-fetch each one. */
  sources:   SemanticSearchResult[];
  /** Informational note (e.g. no model reachable, or no matches). */
  message:   string | null;
  mode:      AIAnswerMode;
  /** True when retrieval fell back to keyword matching because the vendor was out. */
  degraded:  boolean;
  /**
   * The Conversation this Turn was appended to, or null for a one-off
   * question that stored nothing (IR-295).
   */
  conversation_id: number | null;
  /**
   * What retrieval actually searched with, when a follow-up was rewritten
   * into a standalone question (IR-296). Null whenever resolution did not
   * run or changed nothing.
   */
  resolved_question: string | null;
  /**
   * True when this answer left its Conversation's Record scope because the
   * caller asked to search all papers instead of just the one being read
   * (IR-298, ADR-026 §9). Always false with no scope to have left.
   */
  widened: boolean;
}

/**
 * One citation as a stored Turn replays it when its chunk is no longer live
 * (IR-295, degraded by IR-299): record id, chunk id, page, never the quoted
 * text or the record's title. A live chunk replays as a full `Citation`
 * instead — see `ChatCitation`.
 */
export interface ReplayedCitation {
  marker:    number;
  record_id: number;
  chunk_id:  number | null;
  page:      number | null;
}

/** A Passage citation, live or replayed — what the chat UI actually renders. */
export type ChatCitation = Citation | ReplayedCitation;

/** One question-and-answer pair in a persisted Conversation (IR-295). */
export interface ConversationTurn {
  id:                 number;
  question:           string;
  resolved_question:  string | null;
  answer:             string | null;
  message:            string | null;
  state:              AIAnswerMode;
  degraded:           boolean;
  widened:            boolean;
  created_at:         string;
  /** Full `Citation` when the cited chunk is still live, `ReplayedCitation` when it was tombstoned (IR-299). */
  citations:          ChatCitation[];
  /**
   * True when a stream never reached its terminal `done` event (IR-328) —
   * orthogonal to `state`/`mode`, which stay `"generative"`: a partial
   * answer is still an answer a model wrote, just possibly cut short, not
   * the "no answer at all" `unavailable` already means (IR-329). Optional
   * only so existing fixtures/tests that predate this field still type-check
   * — a real response always sends it.
   */
  partial?:           boolean;
}

/** A Conversation without its Turns — the shape a sidebar lists (IR-295). */
export interface ConversationSummary {
  id:            number;
  title:         string;
  record:        number | null;
  record_title:  string | null;
  turn_count:    number;
  created_at:    string;
  updated_at:    string;
}

/** One Conversation with its full transcript (IR-295). */
export interface ConversationDetail extends ConversationSummary {
  turns: ConversationTurn[];
}

export interface EmbeddingJobStatus {
  id:               number;
  record:           number;
  record_title:     string;
  status:           "queued" | "running" | "done" | "failed";
  error:            string | null;
  celery_task_id:   string | null;
  created_at:       string;
  completed_at:     string | null;
}
