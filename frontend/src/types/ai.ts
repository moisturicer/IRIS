export interface SemanticSearchResult {
  id:             number;
  title:          string;
  abstract:       string;
  authors:        string;          // comma-separated display string
  year:           number | null;
  classification: string | null;
  /** PostgreSQL SearchRank. 0 when the substring fallback tier answered. */
  score:          number;
}

/** Which synthesis path produced an answer — surfaced so the UI never implies more than ran. */
export type AIAnswerMode = "generative" | "extractive" | "no_results" | "empty";

export interface AIStatus {
  retrieval:        string;
  generative:       boolean;
  mode:             "generative" | "extractive";
  indexed_records:  number;
}

export interface AIAnswer {
  /** Answer text, or null when nothing in the corpus matched. */
  answer:    string | null;
  /** Record IDs backing the answer. Always readable by the asker. */
  citations: number[];
  /** The retrieved records themselves, so the UI need not re-fetch each one. */
  sources:   SemanticSearchResult[];
  /** Informational note (e.g. retrieval-only mode, or no matches). */
  message:   string | null;
  mode:      AIAnswerMode;
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
