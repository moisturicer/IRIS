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

/**
 * What kind of question each starter is (IR-1306), shown above it so a reader
 * can scan four questions by what they will get back. Presentation only.
 */
export const STARTER_KINDS: Readonly<Record<string, { kind: string; icon: string }>> = {
  [ASK_STARTERS[0]]: { kind: "Topics", icon: "fa-shapes" },
  [ASK_STARTERS[1]]: { kind: "Findings", icon: "fa-flask" },
  [ASK_STARTERS[2]]: { kind: "Data", icon: "fa-database" },
  [ASK_STARTERS[3]]: { kind: "Summary", icon: "fa-align-left" },
  [PAPER_STARTERS[0]]: { kind: "Plain language", icon: "fa-align-left" },
  [PAPER_STARTERS[1]]: { kind: "Method", icon: "fa-diagram-project" },
  [PAPER_STARTERS[2]]: { kind: "Findings", icon: "fa-flask" },
  [PAPER_STARTERS[3]]: { kind: "Data", icon: "fa-database" },
};
