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
  /** Record IDs backing the answer. Always readable by the asker. */
  citations: number[];
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
