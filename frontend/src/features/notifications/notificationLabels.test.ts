import { describe, expect, it } from "vitest";

import { notificationTypeLabel } from "./notificationLabels";

describe("notificationTypeLabel", () => {
  it("replaces the system names the audit found with plain words", () => {
    expect(notificationTypeLabel("New Record (Proposal / Thesis)")).toBe("New submission");
    expect(notificationTypeLabel("Record Routed")).toBe("Sent for review");
    expect(notificationTypeLabel("New Version Submitted")).toBe("New version");
  });

  it("puts a type it has not met in sentence case, without its brackets or suffix", () => {
    expect(notificationTypeLabel("Revision Requested")).toBe("Revision requested");
    expect(notificationTypeLabel("Role Request - Student")).toBe("Role request");
    expect(notificationTypeLabel("Some New Thing (internal)")).toBe("Some new thing");
  });

  it("says nothing for a blank type", () => {
    expect(notificationTypeLabel("")).toBe("");
  });
});
