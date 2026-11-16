import { describe, expect, it } from "vitest";

import { callFailure } from "./callFailure";

const refused = (status: number, detail?: string) => ({ response: { status, data: detail ? { detail } : {} } });

describe("callFailure (IR-765)", () => {
  it("shows the server's refusal of a stale decision, and marks it stale", () => {
    expect(callFailure(refused(409, "This call was changed after you opened it. Reload it and decide again."), "Could not confirm ICCE."))
      .toEqual({ stale: true, message: "This call was changed after you opened it. Reload it and decide again." });
  });

  it("says a call that's gone is gone", () => {
    expect(callFailure(refused(404), "Could not remove ICCE.")).toEqual({
      stale: true, message: "Could not remove ICCE. The call is no longer there.",
    });
  });

  it("leads anything else with what failed, and lets it be tried again", () => {
    const failure = callFailure(new Error("Network Error"), "Could not reject ICCE.");
    expect(failure.stale).toBe(false);
    expect(failure.message).toMatch(/^Could not reject ICCE\./);
  });
});
