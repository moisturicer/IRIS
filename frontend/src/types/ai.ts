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
   * The record's best passage score: cosine similarity, or the reranker's score when
   * one ran, or a PostgreSQL SearchRank on the degraded path. Comparable within one
   * response, not across them.
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
