import type { CitationResolution } from "./useCitationReference";

/**
 * What a reader is told about where a citation landed, when it is not
 * simply the passage, highlighted (IR-578). Every case says what is and is
 * not marked, so nothing reads as a guess. Moved out of the page unchanged
 * (IR-1271).
 */
export function citationLandingNotice(
  resolution: CitationResolution,
  pageContext: boolean,
  page: number | null,
  marked: boolean,
): string | null {
  switch (resolution.status) {
    case "changed":
      // The stored page is from when the answer was written; the paper may
      // have changed since, so it is offered as that, not as the passage.
      return page != null
        ? `The passage this answer quoted has changed since, so nothing is highlighted. Page ${page} is where it was when the answer was written.`
        : "The passage this answer quoted has changed since, so nothing is highlighted.";
    case "missing":
      return "That citation is no longer part of the answer, so nothing is highlighted.";
    case "elsewhere":
      return "That citation points at another paper, so nothing is highlighted here.";
    case "gone":
      return "The answer this citation came from is no longer available, so nothing is highlighted.";
    default:
      if (!pageContext || page == null) return null;
      return marked
        ? `Page context: the Overview drew on page ${page} as a whole, so only page ${page} is marked.`
        : `Page context: the Overview drew on page ${page} as a whole.`;
  }
}
