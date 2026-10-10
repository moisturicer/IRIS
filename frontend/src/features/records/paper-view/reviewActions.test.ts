/**
 * Which assignment *Add reviewer* adds to (IR-418).
 *
 * The server offers `add_reviewer` to anyone holding an open seat on an active
 * office assignment, RDCO's included (`seats.add_reviewer_assignment`). RDCO
 * carries no `office_review` block, so the dialog reads the seat instead; these
 * rows pin that it picks the seat the server would.
 */
import { describe, expect, it } from "vitest";

import type { Party, ReviewerSeat, SeatState } from "@/types/records";

import { addReviewerAssignment } from "./reviewActions";

function seat(party: Party, state: SeatState, assignment: number): ReviewerSeat {
  return {
    id: assignment * 10,
    assignment,
    record: 7,
    party,
    party_label: party.toUpperCase(),
    reviewer: 51,
    reviewer_name: "A Reviewer",
    state,
    state_label: state,
    source: "claimed",
    assigned_by: 51,
    assigned_at: "2026-10-01T08:00:00Z",
    opened_at: null,
    done_at: state === "done" ? "2026-10-03T08:00:00Z" : null,
  };
}

describe("the assignment Add reviewer adds to", () => {
  it("is an RDCO reviewer's open seat, which has no office_review block", () => {
    expect(addReviewerAssignment({ my_seats: [seat("rdco", "in_review", 12)] })).toBe(12);
  });

  it("is a specialist office's open seat, assigned or in review", () => {
    expect(addReviewerAssignment({ my_seats: [seat("ierc", "assigned", 31)] })).toBe(31);
  });

  it("skips a finished seat and the Adviser's, taking the first open office seat", () => {
    const seats = [seat("itso", "done", 5), seat("adviser", "in_review", 6), seat("ktto", "in_review", 8)];
    expect(addReviewerAssignment({ my_seats: seats })).toBe(8);
  });

  it("is none when the viewer holds no open office seat", () => {
    expect(addReviewerAssignment({ my_seats: [seat("adviser", "in_review", 6)] })).toBeNull();
    expect(addReviewerAssignment({ my_seats: [] })).toBeNull();
  });
});
