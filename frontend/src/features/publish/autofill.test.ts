/**
 * A suggested title never ends in ".pdf" (IR-1084, audit WF-04).
 *
 * The server declines a title that is only the manuscript's stored file name,
 * but storage may rename a file ("My_Thesis_k3Jx.pdf"), so the extractor's
 * file-name fallback ("My Thesis.pdf") can reach the client.
 */
import { describe, expect, it } from "vitest";

import type { MetadataSuggestions, SuggestionEntry, SuggestionFields } from "@/types/records";

import { NO_FIELDS, fieldsOf, planAutofill } from "./autofill";

const entry = (value: string): SuggestionEntry<string> => ({
  value, basis: "document_title", page: 1, region: null, auto_apply: true, exceeds_limit: false,
});

const reading = (fields: Partial<SuggestionFields>): MetadataSuggestions => ({
  state: "ready", suggestions: { title: null, abstract: null }, fields: { ...NO_FIELDS, ...fields },
} as unknown as MetadataSuggestions);

describe("fieldsOf: the title", () => {
  it.each([
    ["My Thesis.pdf", "My Thesis"],
    ["My Thesis.PDF", "My Thesis"],
    ["paper.pdf.pdf", "paper"],
    ["Clearance-aware resubmission", "Clearance-aware resubmission"],
  ])("%s is offered as %s", (suggested, offered) => {
    expect(fieldsOf(reading({ title: entry(suggested) })).title?.value).toBe(offered);
  });

  it("offers nothing for a title that was only an extension", () => {
    expect(fieldsOf(reading({ title: entry(".pdf") })).title).toBeNull();
  });

  it("strips the title of a server that sends only the legacy fields", () => {
    const legacy = { state: "ready", suggestions: { title: "My Thesis.pdf", abstract: "An abstract." } } as unknown as MetadataSuggestions;
    const fields = fieldsOf(legacy);
    expect(fields.title?.value).toBe("My Thesis");
    expect(fields.abstract?.value).toBe("An abstract.");
  });

  it("leaves the other fields as the server sent them", () => {
    const abstract = entry("An abstract about a .pdf reader.");
    expect(fieldsOf(reading({ title: entry("A.pdf"), abstract })).abstract).toBe(abstract);
  });
});

describe("planAutofill: the placeholder title", () => {
  it("does not fill a file-name fallback that is the placeholder once its extension is gone", () => {
    const fields = fieldsOf(reading({ title: entry("My Thesis.pdf") }));
    const fills = planAutofill(fields, "r1", { title: { state: "placeholder" } }, {
      title: "My Thesis", abstract: "", authors: [], keywords: "", publication_year: null,
    } as never);
    expect(fills).toEqual([]);
  });

  it("fills a real title without an extension", () => {
    const fields = fieldsOf(reading({ title: entry("Clearance-aware resubmission.pdf") }));
    const fills = planAutofill(fields, "r1", { title: { state: "placeholder" } }, {
      title: "My Thesis", abstract: "", authors: [], keywords: "", publication_year: null,
    } as never);
    expect(fills.map((fill) => fill.value)).toEqual(["Clearance-aware resubmission"]);
  });
});
