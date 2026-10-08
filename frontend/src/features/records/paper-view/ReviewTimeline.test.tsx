/**
 * The Review section's timeline as a reader meets it (IR-412). What goes into
 * it, and in which order, is `timelineEntries.test.ts`'s; this file checks it
 * renders that from the tracker, and that it never presents a retired party
 * such as Intake as where the record is now (spec §0, invariant 1).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { RecordTracker } from "@/types/records";

import { recordsApi } from "@/api/records";

import { ReviewTimeline } from "./ReviewTimeline";

vi.mock("@/api/records", () => ({ recordsApi: { tracker: vi.fn() } }));

const tracker = vi.mocked(recordsApi.tracker);

const payload: RecordTracker = {
  record_id: 7,
  record_type: "Thesis / Research",
  workflow_state: "in_review",
  workflow_state_label: "In review",
  // The legacy pipeline can still hold a record at Intake until IR-260.
  current_holders: [{ party: "intake", label: "Intake (retired)", opened_at: null, opened_by: null }],
  can_act: [],
  parties: [
    {
      party: "intake", label: "Intake (retired)", state: "active", state_label: "Reviewing",
      started: false, outcome: null, outcome_label: null, at: null, preserved: false,
      awaiting_document: null, outcome_earlier: false, in_pool: false, changes_requested: false,
      seats: null,
    },
  ],
  routing_history: [
    {
      group_id: "g1", from: null, from_label: null, to: ["intake"], to_labels: ["Intake (retired)"],
      actor: "Rhea Owner", reason: "", at: "2026-09-01T08:00:00Z",
    },
    {
      group_id: "g2", from: "intake", from_label: "Intake (retired)", to: ["itso"], to_labels: ["ITSO"],
      actor: "Ana Cruz", reason: "Needs an IP check.", at: "2026-09-02T08:00:00Z",
    },
  ],
  routing_recorded_from: null,
  reviews: [
    {
      id: 1, party: "itso", label: "ITSO", status: "approved", status_label: "Approved",
      comment: "Cleared.", reviewed_by_name: "Mara Santos", created_at: "2026-09-05T08:00:00Z", version: null,
    },
  ],
  versions: [],
  resubmissions: [],
  document_requests: null,
  clearances: [],
  resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
};

function respond(data: RecordTracker) {
  tracker.mockResolvedValue({ data } as Awaited<ReturnType<typeof recordsApi.tracker>>);
}

describe("ReviewTimeline", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists what happened, oldest first, with who did it and as which party", async () => {
    respond(payload);
    const { container } = renderScreen(<ReviewTimeline recordId={7} />);

    const list = await screen.findByRole("list", { name: "Review timeline" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent(/^Submitted to Intake \(retired\)/);
    expect(items[1]).toHaveTextContent(/^Routed to ITSO/);
    expect(items[2]).toHaveTextContent(/^Approved/);
    expect(items[1]).toHaveTextContent("Ana Cruz");
    expect(items[1]).toHaveTextContent("Intake (retired)");
    expect(items[1]).toHaveTextContent("Needs an IP check.");
    expect(items[2]).toHaveTextContent("Mara Santos");
    expect(items[2]).toHaveTextContent("ITSO");
    await expectNoBlockingA11yViolations(container);
  });

  it("never presents Intake as where the record is now", async () => {
    respond(payload);
    renderScreen(<ReviewTimeline recordId={7} />);

    await screen.findByRole("list", { name: "Review timeline" });
    // The tracker says Intake holds the record; the timeline says nothing of
    // where it is now, Intake least of all.
    expect(screen.queryByText(/currently with|current step|now with/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^now$/i)).not.toBeInTheDocument();
  });

  it("shows each version, and which version a review was made against", async () => {
    respond({
      ...payload,
      versions: [
        {
          number: 1, cause: "submission", cause_label: "Submission",
          created_at: "2026-09-01T09:00:00Z", created_by_name: "Rhea Owner",
          manuscript_url: "/api/v1/records/7/versions/1/manuscript/",
        },
      ],
      reviews: [{ ...payload.reviews![0], version: 1 }],
    });
    const { container } = renderScreen(<ReviewTimeline recordId={7} />);

    const list = await screen.findByRole("list", { name: "Review timeline" });
    const submitted = within(list).getByText("v1 submitted").closest("li")!;
    const approved = within(list).getByText("Approved").closest("li")!;
    expect(submitted).toHaveTextContent("Rhea Owner");
    expect(approved).toHaveTextContent("Made against v1");
    await expectNoBlockingA11yViolations(container);
  });

  it("says so when nothing has happened yet", async () => {
    respond({ ...payload, routing_history: [], reviews: [] });
    renderScreen(<ReviewTimeline recordId={7} />);

    expect(await screen.findByText("Nothing has happened in this review yet.")).toBeInTheDocument();
  });

  it("says routing before a date was not recorded, rather than imply there was none", async () => {
    respond({ ...payload, routing_recorded_from: "2026-08-15T00:00:00Z" });
    renderScreen(<ReviewTimeline recordId={7} />);

    expect(await screen.findByText("Routing recorded from Aug 15, 2026.")).toBeInTheDocument();
  });

  it("offers to try again when the tracker cannot be loaded", async () => {
    tracker.mockRejectedValueOnce(new Error("offline"));
    respond(payload);
    renderScreen(<ReviewTimeline recordId={7} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the review timeline.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("list", { name: "Review timeline" })).toBeInTheDocument();
    expect(tracker).toHaveBeenCalledTimes(2);
  });
});
