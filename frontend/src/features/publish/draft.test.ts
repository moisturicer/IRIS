/**
 * Publish's pure rules (IR-408), as tables.
 */
import { describe, expect, it } from "vitest";

import { emptyMetadata } from "@/features/records/metadata/metadataSchema";

import { describeFailure, firstIncompleteStep, provisionalTitle } from "./draft";

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

  const cases: Array<{ label: string; draft: Parameters<typeof firstIncompleteStep>[0]; step: number }> = [
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
    expect(firstIncompleteStep(draft, 7)).toBe(step);
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
