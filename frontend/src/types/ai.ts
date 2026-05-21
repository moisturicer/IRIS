export interface SemanticSearchResult {
  id:       number;
  title:    string;
  abstract: string | null;
  authors:  string | null;    // comma-separated display string
  year:     number | null;
  score:    number;           // cosine similarity 0..1
}

export interface AIAnswer {
  answer:      string;
  /** Record IDs cited in the answer -- can be used to add reference links */
  citations:   number[];
}

export interface EmbeddingJobStatus {
  id:             number;
  record:         number;
  record_title:   string;
  status:         "queued" | "running" | "done" | "failed";
  error:          string | null;
  created_at:     string;
  completed_at:   string | null;
}
