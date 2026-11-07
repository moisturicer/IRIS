import { describe, expect, it } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";

import { readFailureKind } from "./readFailure";

describe("readFailureKind", () => {
  it("calls a timeout interrupted", () => {
    expect(readFailureKind(new RequestTimeoutError(30_000))).toBe("interrupted");
  });

  it("answers 403 and 404 alike, so a hidden Record cannot be told from a missing id", () => {
    expect(readFailureKind({ response: { status: 404 } })).toBe("unavailable");
    expect(readFailureKind({ response: { status: 403 } })).toBe("unavailable");
  });

  it("calls everything else failed", () => {
    expect(readFailureKind({ response: { status: 500 } })).toBe("failed");
    expect(readFailureKind(new Error("Network Error"))).toBe("failed");
    expect(readFailureKind(null)).toBe("failed");
  });
});
