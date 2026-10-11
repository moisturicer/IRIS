/**
 * My Reviews' own small rules (IR-268): the URL contract and how a row is
 * worded. Kept out of the page so they are tested without a DOM, as
 * `queueFilters` was before it.
 */
import { describe, expect, it } from "vitest";

import type { MyReviewsRow } from "@/types/reviews";

import { holderLine, readView, routingLine, viewSearch, waitLabel } from "./myReviews";

function row(overrides: Partial<MyReviewsRow> = {}): MyReviewsRow {
  return {
    key: "seat:1", kind: "seat", record: 7, title: "Smart Campus Energy Monitor",
    record_type_name: "Thesis / Research", party: "itso", party_label: "ITSO",
    seat: 1, assignment: 3, holder: 9, holder_name: "Ana Reyes",
    is_mine: true, routed_by: null, routed_reason: "", submitted_by: null,
    waiting_since: "2026-10-01T00:00:00Z", waiting_days: 2, waiting_on: null,
    outcome: null, outcome_label: null, decided_at: null,
    can_claim: false, can_assign: false,
    ...overrides,
  };
}

describe("readView", () => {
  it("defaults to To review, every outcome, and your own reviews", () => {
    expect(readView(new URLSearchParams())).toEqual({
      view: { tab: "to_review", outcome: null, office: null },
      replace: null,
    });
  });

  it("reads the tab, the outcome and the office from the URL", () => {
    const { view } = readView(new URLSearchParams("tab=done&outcome=finding&office=itso"));
    expect(view).toEqual({ tab: "done", outcome: "finding", office: "itso" });
  });

  it("treats an unknown tab or outcome as the default, since the URL is untrusted", () => {
    const { view } = readView(new URLSearchParams("tab=awaiting&outcome=approved"));
    expect(view).toEqual({ tab: "to_review", outcome: null, office: null });
  });

  it("drops an outcome outside Done, where it filters nothing", () => {
    expect(readView(new URLSearchParams("tab=in_review&outcome=cleared")).view.outcome).toBeNull();
  });

  it("never offers revision_requested as a filter", () => {
    expect(readView(new URLSearchParams("tab=done&outcome=revision_requested")).view.outcome).toBeNull();
  });

  it.each([
    ["pending", "to_review"],
    ["approved", "done"],
    ["declined", "done"],
  ] as const)("translates an old ?status=%s bookmark to %s, once", (status, tab) => {
    const { view, replace } = readView(new URLSearchParams(`status=${status}`));
    expect(view.tab).toBe(tab);
    expect(replace).toBe(viewSearch(view));
  });
});

describe("viewSearch", () => {
  it("leaves every default out of the URL", () => {
    expect(viewSearch({ tab: "to_review", outcome: null, office: null })).toBe("");
  });

  it("keeps what differs from the default", () => {
    expect(viewSearch({ tab: "done", outcome: "cleared", office: "itso" }))
      .toBe("tab=done&outcome=cleared&office=itso");
  });
});

describe("holderLine", () => {
  it("names the office and you on your own seat", () => {
    expect(holderLine(row())).toBe("ITSO · You");
  });

  it("names a colleague's seat by its holder", () => {
    expect(holderLine(row({ is_mine: false }))).toBe("ITSO · Ana Reyes");
  });

  it("marks an unclaimed record Unassigned", () => {
    expect(holderLine(row({ kind: "pool", holder: null, holder_name: null, is_mine: false })))
      .toBe("ITSO · Unassigned");
  });

});

describe("routingLine", () => {
  it("says who routed it and why", () => {
    expect(routingLine(row({ routed_by: "Prof. Santos", routed_reason: "Potential IP concern" })))
      .toBe("Routed by Prof. Santos · “Potential IP concern”");
  });

  it("says who submitted it, for an Adviser's own seat", () => {
    expect(routingLine(row({ submitted_by: "Juan Dela Cruz" }))).toBe("Submitted by Juan Dela Cruz");
  });

  it("names IRIS when nobody routed it by hand", () => {
    expect(routingLine(row({ routed_reason: "Specialist review complete" })))
      .toBe("Handed back by IRIS · “Specialist review complete”");
  });

  it("says nothing when nothing is known", () => {
    expect(routingLine(row())).toBeNull();
  });
});

describe("waitLabel", () => {
  it("says Today rather than 0 days", () => {
    expect(waitLabel(0)).toBe("Today");
    expect(waitLabel(1)).toBe("1 day");
    expect(waitLabel(9)).toBe("9 days");
  });
});
