import { describe, expect, it } from "vitest";
import type { RecordListItem } from "@/types/records";
import { buildCitation, recordYear } from "./discoverUtils";

const reference = {
  id: 91, title: "An external study", authors: [], origin: "imported_reference",
  publication_year: null, year_accomplished: 2020, created_at: "2026-10-01T00:00:00Z",
} as unknown as RecordListItem;

describe("truthful citation metadata", () => {
  it("uses an authorless citation and never presents completion or added year as publication", () => {
    expect(recordYear(reference)).toBeNull();
    expect(buildCitation(reference, "APA")).toBe("An external study. (n.d.).");
    expect(buildCitation(reference, "MLA")).toBe('"An external study." n.d.');
    expect(buildCitation(reference, "BibTeX")).not.toMatch(/author\s*=|institution\s*=|2020|2026/);
  });
  it("preserves recorded authors and publication year for external work", () => {
    expect(buildCitation({ ...reference, authors: [{ id: 1, name: "Ada Reyes", role: null }], publication_year: 2017 }, "APA"))
      .toBe("Reyes, A. (2017). An external study.");
  });
});
