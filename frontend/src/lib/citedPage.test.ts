import { describe, expect, it } from "vitest";

import { citationNavigationState, citedPage } from "./citedPage";
import type { Citation, ReplayedCitation } from "@/types/ai";

describe("the page a citation asked for", () => {
  it("reads a page number off the query string", () => {
    expect(citedPage("12")).toBe(12);
  });

  it("ignores an absent or empty value", () => {
    expect(citedPage(null)).toBeNull();
    expect(citedPage("")).toBeNull();
    expect(citedPage("   ")).toBeNull();
  });

  it("ignores anything that is not a positive whole page", () => {
    // The query string is whatever was typed into the address bar. None of
    // these name a page, so none of them reach the viewer.
    expect(citedPage("0")).toBeNull();
    expect(citedPage("-3")).toBeNull();
    expect(citedPage("2.5")).toBeNull();
    expect(citedPage("twelve")).toBeNull();
    expect(citedPage("12; drop")).toBeNull();
  });
});

// `paperHrefAtPage` (the `#page=N` fragment link to a raw PDF URL) and its
// three tests above are deleted, deliberately, not merely outdated (IR-335):
// IR-334 put the manuscript behind `IsAuthenticated`, and a plain `<a href>`
// navigation built from that function carries no `Authorization` header, so
// every link it produced now 401s. `PaperPdfReader` fetches the file through
// `apiClient` instead, and `citationNavigationState` below replaces the
// paper-URL-as-string approach with the citation itself.

const liveCitation: Citation = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page:         12,
  text:         "the network reduced mean absolute error by twelve per cent",
  context_path: ["Flood Prediction", "Results"],
  regions:      [{ page: 12, left: 0.1, top: 0.2, right: 0.6, bottom: 0.3 }],
};

const replayedCitation: ReplayedCitation = {
  marker:    2,
  record_id: 7,
  chunk_id:  null,
  page:      3,
};

describe("carrying a citation to the paper view", () => {
  it("wraps a live citation, regions included, for router state", () => {
    expect(citationNavigationState(liveCitation)).toEqual({ citation: liveCitation });
  });

  it("wraps a replayed citation the same way, with no regions to carry", () => {
    expect(citationNavigationState(replayedCitation)).toEqual({ citation: replayedCitation });
  });
});
