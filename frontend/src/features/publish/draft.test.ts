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

  it("says the network failed when there was no response at all", () => {
    const failure = describeFailure(new Error("Network Error"), "fallback");
    expect(failure.network).toBe(true);
    expect(failure.message).toMatch(/couldn't reach IRIS/);
  });
});
