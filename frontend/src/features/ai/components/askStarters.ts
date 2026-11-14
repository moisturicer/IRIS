/**
 * Questions an empty Ask IRIS conversation offers to start from (IR-1090).
 *
 * Fixed wording, not built from the corpus, and each one is a whole question: it
 * is sent as it stands, so none has a blank for the reader to fill in. They say
 * what kind of question the assistant answers well, so a reader who does not
 * know what to ask has somewhere to begin. They name no institution (IR-768) and read the same on
 * any deployment. Presentation only: asking one is an ordinary question.
 */
export const ASK_STARTERS: readonly string[] = [
  "What are the most common research topics across the repository?",
  "Which recent papers report experimental results, and what did they find?",
  "What datasets or data sources do the papers rely on most?",
  "Summarize the main findings of the most recent papers.",
];

/** The same, for Ask IRIS opened on one paper. */
export const PAPER_STARTERS: readonly string[] = [
  "Summarize this paper in plain language.",
  "What method does this paper use, and why?",
  "What are the main findings and limitations of this paper?",
  "What does this paper say about its data?",
];
