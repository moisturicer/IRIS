import { describe, expect, it } from "vitest";
import { errorDetail } from "./errorDetail";

describe("reader-facing API errors", () => {
  it("prefers Retry-After and rounds the wait upward", () => {
    expect(errorDetail({ response: { status: 429, headers: { "retry-after": "841" }, data: {
      detail: "Request was throttled. Expected available in 30 seconds.",
    } } }, "Failed")).toBe("Too many requests — try again in about 15 minutes.");
  });

  it("uses the DRF detail when the header is missing or malformed", () => {
    expect(errorDetail({ response: { status: 429, headers: { "retry-after": "invalid" }, data: {
      detail: "Request was throttled. Expected available in 3601 seconds.",
    } } }, "Failed")).toBe("Too many requests — try again in about 2 hours.");
  });

  it.each([
    [1, "1 second"], [59, "59 seconds"], [60, "1 minute"],
    [61, "2 minutes"], [3600, "1 hour"], [54000, "15 hours"],
  ])("formats a %s-second wait as %s", (seconds, wait) => {
    expect(errorDetail({ response: { status: 429, headers: { "retry-after": String(seconds) } } }, "Failed"))
      .toBe(`Too many requests — try again in about ${wait}.`);
  });

  it.each([undefined, "", "invalid", "-1", "Infinity"])("gives a useful fallback for an unusable header %s", (header) => {
    expect(errorDetail({ response: { status: 429, headers: { "retry-after": header } } }, "Failed"))
      .toBe("Too many requests — try again later.");
  });

  it("uses a headerless DRF wait", () => {
    expect(errorDetail({ response: { status: 429, data: { detail: "Request was throttled. Expected available in 30 seconds." } } }, "Failed"))
      .toBe("Too many requests — try again in about 30 seconds.");
  });

  it("preserves another server refusal", () => {
    expect(errorDetail({ response: { status: 403, data: { detail: "You cannot review this record." } } }, "Failed"))
      .toBe("You cannot review this record.");
  });

  it.each([null, new Error("network"), { response: { status: 500 } }, { response: { data: { detail: {} } } }])("keeps the screen's fallback without a server detail", (error) => {
    expect(errorDetail(error, "The upload failed.")).toBe("The upload failed.");
  });
});
