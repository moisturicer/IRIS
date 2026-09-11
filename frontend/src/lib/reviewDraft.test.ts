/**
 * The reviewer's unsent decision, kept across a navigation (IR-237).
 *
 * This exists because the evaluation screen stopped opening new tabs. The two
 * links to the evidence used to escape the page so the form would not unmount
 * and lose a typed comment (IR-143); now they navigate in-tab and the draft is
 * what protects the comment instead — better, because it also survives an
 * accidental back, a crash, and a session expiry, none of which a new tab did.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { clearReviewDraft, readReviewDraft, writeReviewDraft } from "./reviewDraft";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("the review draft", () => {
  it("gives back what was written", () => {
    writeReviewDraft(42, { status: "declined", comment: "Section 3 needs consent forms." });

    expect(readReviewDraft(42)).toEqual({
      status: "declined",
      comment: "Section 3 needs consent forms.",
    });
  });

  it("keeps each record's draft to itself", () => {
    // Two records open in one session must not bleed into each other: a
    // comment written about one submission appearing under another is worse
    // than losing it, because the reviewer might not notice.
    writeReviewDraft(42, { status: "declined", comment: "About forty-two." });
    writeReviewDraft(43, { status: "rejected", comment: "About forty-three." });

    expect(readReviewDraft(42)?.comment).toBe("About forty-two.");
    expect(readReviewDraft(43)?.comment).toBe("About forty-three.");
  });

  it("has nothing to give back for a record never written", () => {
    expect(readReviewDraft(99)).toBeNull();
  });

  it("forgets a draft once it is cleared", () => {
    writeReviewDraft(42, { status: "declined", comment: "Superseded." });

    clearReviewDraft(42);

    expect(readReviewDraft(42)).toBeNull();
  });

  it("stores nothing for an untouched form", () => {
    // "Approve, no comment" is the form's own default, so persisting it would
    // fill storage with drafts nobody wrote and make "is there a draft?"
    // permanently true.
    writeReviewDraft(42, { status: "approved", comment: "" });

    expect(readReviewDraft(42)).toBeNull();
    expect(sessionStorage.length).toBe(0);
  });

  it("treats whitespace as untouched", () => {
    writeReviewDraft(42, { status: "approved", comment: "   \n  " });

    expect(readReviewDraft(42)).toBeNull();
  });

  it("keeps a non-default decision even with no comment", () => {
    // Choosing "Request Revision" is itself a decision worth not losing, even
    // before the reviewer has justified it.
    writeReviewDraft(42, { status: "declined", comment: "" });

    expect(readReviewDraft(42)).toEqual({ status: "declined", comment: "" });
  });

  it("replaces an earlier draft rather than accumulating", () => {
    writeReviewDraft(42, { status: "declined", comment: "First thought." });
    writeReviewDraft(42, { status: "rejected", comment: "Second thought." });

    expect(readReviewDraft(42)).toEqual({ status: "rejected", comment: "Second thought." });
    expect(sessionStorage.length).toBe(1);
  });

  it("refuses a stored value that is not a draft", () => {
    // sessionStorage is editable by anyone at the console, and a shape that
    // does not match must not reach the form as a decision.
    sessionStorage.setItem("iris_review_draft:42", "not json at all");
    expect(readReviewDraft(42)).toBeNull();

    sessionStorage.setItem("iris_review_draft:42", JSON.stringify({ status: "obliterated" }));
    expect(readReviewDraft(42)).toBeNull();

    sessionStorage.setItem("iris_review_draft:42", JSON.stringify({ status: "approved", comment: 7 }));
    expect(readReviewDraft(42)).toBeNull();
  });

  it("survives a browser that refuses storage entirely", () => {
    // Site data can be blocked, and in a private window the accessor itself
    // throws. The reviewer loses the draft, which is a shame; they must not
    // lose the form, which would be a defect.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("access denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("access denied");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("access denied");
    });

    expect(() => writeReviewDraft(42, { status: "declined", comment: "x" })).not.toThrow();
    expect(readReviewDraft(42)).toBeNull();
    expect(() => clearReviewDraft(42)).not.toThrow();
  });
});
