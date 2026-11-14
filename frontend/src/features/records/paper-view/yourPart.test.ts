import { describe, expect, it } from "vitest";

import type { Readiness, ReadinessItem, ReviewerSeat } from "@/types/records";

import { readinessFacts, yourPartSummary } from "./yourPart";

const item = (over: Partial<ReadinessItem>): ReadinessItem => ({
  kind: "open_thread", severity: "info", label: "A fact.", party: null, actor_name: null,
  since: null, paused: null, action: null, ...over,
});
const readiness = (verdict: Readiness["verdict"], headline: string, items: ReadinessItem[] = []): Readiness =>
  ({ verdict, headline, items });
const seat = (over: Partial<ReviewerSeat>) => ({ state: "in_review", state_label: "In review", ...over }) as ReviewerSeat;

describe("the footer's one heading and one line (IR-1094)", () => {
  it("says the server's headline, never a sentence of the browser's own", () => {
    const part = yourPartSummary({
      readiness: readiness("waiting_on_you", "Ready to clear or record a finding."),
      seat: seat({}), draftCount: 0,
    });
    expect(part.heading).toBe("Ready to clear or record a finding.");
    expect(part.line).toBeNull();
    expect(part.icon).toBe("fa-circle-exclamation");
  });

  it("shows a finished review's verdict instead of a 'not in review' warning (WF-07)", () => {
    const part = yourPartSummary({
      readiness: readiness("none", "This record is not in review."),
      seat: seat({ state: "done", state_label: "Done", verdict_label: "Cleared" }), draftCount: 0,
    });
    expect(part.heading).toBe("Your review: Cleared");
    expect(part.line).toBeNull();
    expect(part.icon).toBe("fa-circle-check");
  });

  it("falls back to the seat's own state when the server discloses no readiness", () => {
    expect(yourPartSummary({ readiness: null, seat: seat({ state: "assigned", state_label: "Assigned" }), draftCount: 0 }))
      .toMatchObject({ heading: "Your review: Assigned", line: null });
    expect(yourPartSummary({ readiness: null, seat: undefined, draftCount: 0 }).heading)
      .toBe("Your review: No verdict recorded");
  });

  it("puts the most severe fact on the line, with the drafts held beside it", () => {
    const part = yourPartSummary({
      readiness: readiness("blocked", "You can't decide yet.", [
        item({ severity: "blocker", label: "ITSO asked the author for a revision.", kind: "revision_request" }),
        item({ label: "ITSO has 1 open thread." }),
      ]),
      seat: undefined, draftCount: 3,
    });
    expect(part.line).toBe("ITSO asked the author for a revision. · 3 draft comments, not sent");
    expect(yourPartSummary({
      readiness: readiness("blocked", "You can't decide yet.", [item({ severity: "blocker", label: "Open the review first." })]),
      seat: undefined, draftCount: 0,
    }).line).toBe("Open the review first.");
  });

  it("says how many drafts are held when there is no blocker", () => {
    const part = yourPartSummary({
      readiness: readiness("waiting_on_you", "Ready to clear or record a finding.", [item({ label: "ITSO is due 22 Nov.", kind: "due_date" })]),
      seat: seat({}), draftCount: 2,
    });
    expect(part.line).toBe("2 draft comments, not sent");
    expect(yourPartSummary({ readiness: null, seat: seat({}), draftCount: 1 }).line).toBe("1 draft comment, not sent");
  });

  it("takes the first fact for the line when there is no blocker and no draft", () => {
    const part = yourPartSummary({
      readiness: readiness("none", "Nothing here waits on you.", [item({ label: "ITSO is due 22 Nov.", kind: "due_date" })]),
      seat: undefined, draftCount: 0,
    });
    expect(part.line).toBe("ITSO is due 22 Nov.");
  });
});

describe("what the footer leaves to Details (US-17)", () => {
  it("drops the facts that restate a party's status, because Reviewers says it once", () => {
    const facts = readinessFacts(readiness("none", "Nothing here waits on you.", [
      item({ kind: "party_reviewing", label: "ITSO is reviewing." }),
      item({ kind: "pool_unclaimed", label: "Nobody at IERC has claimed this review yet." }),
      item({ kind: "due_date", label: "ITSO is due 22 Nov." }),
    ]));
    expect(facts.map((f) => f.kind)).toEqual(["due_date"]);
  });

  it("gives the line only a fact that is not about a party's status", () => {
    const part = yourPartSummary({
      readiness: readiness("none", "Nothing here waits on you.", [item({ kind: "party_reviewing", label: "ITSO is reviewing." })]),
      seat: undefined, draftCount: 0,
    });
    expect(part.line).toBeNull();
  });
});
