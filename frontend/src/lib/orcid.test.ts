import { describe, expect, it } from "vitest";

import { orcidProblem } from "./orcid";

describe("orcidProblem", () => {
  it.each([
    "0000-0002-1825-0097", // ORCID's own documentation example
    "0000-0001-5109-3700",
    "0000-0002-1694-233X", // check digit X
    "0000-0002-1694-233x", // lowercase X
  ])("accepts the valid iD %s", (id) => {
    expect(orcidProblem(id)).toBeNull();
  });

  it("accepts an empty field, because the iD is optional", () => {
    expect(orcidProblem("")).toBeNull();
    expect(orcidProblem("   ")).toBeNull();
  });

  it.each(["0000-0002-1825", "0000000218250097", "0000-0002-1825-009A", "https://orcid.org/0000-0002-1825-0097"])(
    "names the expected format for %s",
    (id) => {
      expect(orcidProblem(id)).toBe("Enter an ORCID iD like 0000-0002-1825-0097.");
    },
  );

  it("says when the last character does not match the rest", () => {
    expect(orcidProblem("0000-0002-1825-0098")).toBe(
      "This ORCID iD doesn't check out — look for a mistyped digit.",
    );
  });
});
