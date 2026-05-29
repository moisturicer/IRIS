export interface SemanticSearchResult {
  id:       number;
  title:    string;
  abstract: string | null;
  authors:  string | null;    // comma-separated display string
  year:     number | null;
  score:    number;           // cosine similarity 0..1
}

export interface AIAnswer {
  /** LLM-generated answer string, or null while RAG answer generation is not yet implemented. */
  answer:    string | null;
  /** Record IDs of the top-k most relevant records retrieved by semantic similarity. */
  citations: number[];
  /** Informational message returned by the backend (e.g. when the knowledge base is empty). */
  message:   string | null;
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
