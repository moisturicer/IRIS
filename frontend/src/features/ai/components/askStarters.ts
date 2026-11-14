/**
 * Questions an empty Ask IRIS conversation offers to start from (IR-1090).
 *
 * Fixed wording, not built from the corpus: they say what kind of question the
 * assistant answers well, so a reader who does not know what to ask has
 * somewhere to begin. They name no institution (IR-768) and read the same on
 * any deployment. Presentation only: asking one is an ordinary question.
 */
export const ASK_STARTERS: readonly string[] = [
  "What research has been published on this topic?",
  "Compare the methods used in two papers I name.",
  "Which papers report results on a measure I describe?",
  "Summarize what is known about a problem, with citations.",
];

/** The same, for Ask IRIS opened on one paper. */
export const PAPER_STARTERS: readonly string[] = [
  "Summarize this paper in plain language.",
  "What method does this paper use, and why?",
  "What are the main findings and limitations of this paper?",
  "What does this paper say about its data?",
];
