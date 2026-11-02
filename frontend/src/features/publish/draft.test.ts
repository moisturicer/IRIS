/**
 * Publish's pure rules (IR-408), as tables.
 */
import { describe, expect, it } from "vitest";

import { emptyMetadata } from "@/features/records/metadata/metadataSchema";

import {
  describeFailure,
  embargoAnswer,
  embargoFromDraft,
  embargoProblem,
  firstIncompleteStep,
  provisionalTitle,
  sameEmbargo,
  type EmbargoChoice,
} from "./draft";

describe("provisionalTitle", () => {
  it.each([
    ["My_Clearance-Study.pdf", "My Clearance Study"],
    ["thesis final.v2.PDF", "thesis final.v2"],
    ["  spaced__out--name .pdf", "spaced out name"],
    [".pdf", "Untitled manuscript"],
  ])("%s → %s", (fileName, title) => {
    expect(provisionalTitle(fileName)).toBe(title);
  });
});

describe("firstIncompleteStep", () => {
  const complete = {
    ...emptyMetadata("Ada Reyes"),
    title: "Clearance-aware resubmission",
    abstract: "An abstract that is comfortably longer than thirty characters.",
    adviser: 21,
  };

  const answered: EmbargoChoice = { choice: "no", until: "" };

  const cases: Array<{ label: string; draft: Omit<Parameters<typeof firstIncompleteStep>[0], "embargo">; step: number }> = [
    { label: "no type", draft: { typeId: null, hasManuscript: true, values: complete }, step: 1 },
    { label: "no manuscript", draft: { typeId: 2, hasManuscript: false, values: complete }, step: 1 },
    { label: "no abstract", draft: { typeId: 2, hasManuscript: true, values: { ...complete, abstract: "" } }, step: 2 },
    {
      label: "no adviser",
      draft: { typeId: 2, hasManuscript: true, values: { ...complete, adviser: undefined as unknown as number } },
      step: 2,
    },
    { label: "the author as adviser", draft: { typeId: 2, hasManuscript: true, values: { ...complete, adviser: 7 } }, step: 2 },
    { label: "everything", draft: { typeId: 2, hasManuscript: true, values: complete }, step: 3 },
  ];

  it.each(cases)("$label → step $step", ({ draft, step }) => {
    expect(firstIncompleteStep({ embargo: answered, ...draft }, 7)).toBe(step);
  });

  it("asks the embargo question before anything else, even on a complete draft", () => {
    const draft = { typeId: 2, hasManuscript: true, values: complete };

    expect(firstIncompleteStep({ ...draft, embargo: { choice: null, until: "" } }, 7)).toBe(0);
  });
});

describe("the embargo question's rules", () => {
  const TODAY = "2026-11-02";

  it.each<[string, EmbargoChoice, string | null, string | null]>([
    ["unanswered", { choice: null, until: "" }, "embargoed", "Say whether this paper is under embargo."],
    ["no", { choice: "no", until: "" }, null, null],
    ["no, with a date left over from an earlier Yes", { choice: "no", until: "2027-01-01" }, null, null],
    ["yes with no date", { choice: "yes", until: "" }, "embargoed_until", "Choose the date to review this embargo."],
    ["yes with a past date", { choice: "yes", until: "2026-11-01" }, "embargoed_until", "The date to review this embargo cannot be in the past."],
    ["yes with today", { choice: "yes", until: TODAY }, null, null],
    ["yes with a later date", { choice: "yes", until: "2027-03-01" }, null, null],
  ])("%s", (_label, value, field, message) => {
    const problem = embargoProblem(value, TODAY);

    expect(problem?.field ?? null).toBe(field);
    expect(problem?.message ?? null).toBe(message);
  });

  it("refuses to read unanswered as No, which can send text out", () => {
    expect(() => embargoAnswer({ choice: null, until: "" })).toThrow();
  });

  it.each<[string, EmbargoChoice | null, EmbargoChoice, boolean]>([
    ["nothing saved", null, { choice: "no", until: "" }, false],
    ["the same No", { choice: "no", until: "" }, { choice: "no", until: "" }, true],
    ["a No with a leftover date", { choice: "no", until: "" }, { choice: "no", until: "2027-01-01" }, true],
    ["the same Yes", { choice: "yes", until: "2027-01-01" }, { choice: "yes", until: "2027-01-01" }, true],
    ["a Yes with a new date", { choice: "yes", until: "2027-01-01" }, { choice: "yes", until: "2027-02-01" }, false],
    ["No changed to Yes", { choice: "no", until: "" }, { choice: "yes", until: "2027-02-01" }, false],
  ])("sameEmbargo: %s", (_label, saved, value, same) => {
    expect(sameEmbargo(saved, value)).toBe(same);
  });

  it("sends no date with a No, even one left over from an earlier Yes", () => {
    expect(embargoAnswer({ choice: "no", until: "2027-01-01" })).toEqual({ embargoed: false, embargoed_until: null });
    expect(embargoAnswer({ choice: "yes", until: "2027-01-01" })).toEqual({ embargoed: true, embargoed_until: "2027-01-01" });
  });

  it.each<[string, Parameters<typeof embargoFromDraft>[0]["embargo"], EmbargoChoice]>([
    ["no embargo", { state: "none", until: null }, { choice: "no", until: "" }],
    ["active", { state: "active", until: "2027-03-01" }, { choice: "yes", until: "2027-03-01" }],
    ["unknown", { state: "unknown", until: null }, { choice: null, until: "" }],
    ["released", { state: "released", until: "2027-03-01" }, { choice: null, until: "" }],
    ["not disclosed", null, { choice: null, until: "" }],
    ["an older API", undefined, { choice: null, until: "" }],
  ])("a draft with %s", (_label, embargo, expected) => {
    expect(embargoFromDraft({ embargo } as Parameters<typeof embargoFromDraft>[0])).toEqual(expected);
  });
});

describe("describeFailure", () => {
  it("separates the message from the field errors", () => {
    const failure = describeFailure(
      { response: { status: 400, data: { detail: "Not yet.", title: ["Too short.", "Really."] } } },
      "fallback",
    );
    expect(failure).toEqual({ message: "Not yet.", fields: { title: "Too short. Really." }, network: false });
  });

  it("uses the fallback when the server gives only field errors", () => {
    expect(describeFailure({ response: { data: { adviser: ["Required."] } } }, "Fallback.").message).toBe("Fallback.");
  });

  // IR-610: a server error with nothing readable in it named the file, not the server.
  it.each([
    ["a 500 with an empty body", 500, ""],
    ["a 502 with an HTML body", 502, "<html><body><h1>502 Bad Gateway</h1></body></html>"],
    ["a 504 with no body", 504, undefined],
    ["a 502 with a proxy's plain-text body", 502, "upstream connect error or disconnect/reset before headers"],
  ])("says IRIS is not responding for %s", (_label, status, data) => {
    const failure = describeFailure({ response: { status, data } }, "The upload failed.");
    expect(failure.message).toMatch(/IRIS isn't responding/);
    expect(failure.network).toBe(false);
  });

  it.each([
    ["an empty body", ""],
    ["nginx's error page", "<html><head><title>413 Request Entity Too Large</title></head></html>"],
  ])("says it is too large for a 413 with %s", (_label, data) => {
    const failure = describeFailure({ response: { status: 413, data } }, "The upload failed.");
    expect(failure.message).toMatch(/too large/);
  });

  it("shows a short plain reply from IRIS itself, trimmed", () => {
    expect(describeFailure({ response: { status: 400, data: "Bad request.\n\n" } }, "fallback").message).toBe("Bad request.");
  });

  it("keeps the server's own message over the status", () => {
    const failure = describeFailure({ response: { status: 503, data: { detail: "Down for maintenance." } } }, "fallback");
    expect(failure.message).toBe("Down for maintenance.");
  });

  it("keeps the fallback for a 400 that carries only field errors", () => {
    const failure = describeFailure({ response: { status: 400, data: { abstract_file: ["Only PDF files are accepted."] } } }, "Fallback.");
    expect(failure).toEqual({ message: "Fallback.", fields: { abstract_file: "Only PDF files are accepted." }, network: false });
  });

  it("says the network failed when there was no response at all", () => {
    const failure = describeFailure(new Error("Network Error"), "fallback");
    expect(failure.network).toBe(true);
    expect(failure.message).toMatch(/couldn't reach IRIS/);
  });
});
