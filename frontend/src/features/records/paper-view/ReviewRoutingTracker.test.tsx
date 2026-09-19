/**
 * The Review & Routing Tracker panel on the paper view (IR-258).
 *
 * Everything the panel says comes from `GET /records/<id>/tracker/`; nothing is
 * worked out here (workflow_routing_architecture.md §9.1). These cases feed it
 * the payloads the backend's `test_tracker.py` pins for the same situations,
 * and check what a reader of the page -- or a screen reader -- is told.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { RecordTracker, TrackerPartyRow } from "@/types/records";

import { ReviewRoutingTracker } from "./ReviewRoutingTracker";

const tracker = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: { tracker: (id: number) => tracker(id) },
}));

const RECORD_ID = 12;

function row(
  party: TrackerPartyRow["party"],
  label: string,
  state: TrackerPartyRow["state"],
  extra: Partial<TrackerPartyRow> = {},
): TrackerPartyRow {
  const stateLabels = {
    active: "Active",
    completed: "Completed",
    withdrawn: "Withdrawn",
    not_requested: "Not requested",
    awaiting: "Awaiting",
  } as const;
  return {
    party,
    label,
    state,
    state_label: stateLabels[state],
    started: false,
    outcome: null,
    outcome_label: null,
    at: state === "not_requested" || state === "awaiting" ? null : "2026-09-18T02:00:00Z",
    preserved: false,
    ...extra,
  };
}

function payload(overrides: Partial<RecordTracker>): RecordTracker {
  return {
    record_id: RECORD_ID,
    record_type: "Thesis / Research",
    workflow_state: "submitted",
    workflow_state_label: "Submitted",
    current_holders: [],
    can_act: [],
    parties: [],
    routing_history: [],
    routing_recorded_from: "2026-09-19T12:00:00Z",
    reviews: [],
    resubmissions: [],
    document_requests: [],
    clearances: [],
    resubmission: {
      count: 0,
      last_resubmitted_at: null,
      declining_office: null,
      offices_preserved: [],
    },
    ...overrides,
  };
}

const thesisAtIntake = payload({
  current_holders: [
    { party: "intake", label: "Intake & Triage", opened_at: "2026-09-18T02:00:00Z", opened_by: null },
  ],
  parties: [
    row("intake", "Intake & Triage", "active"),
    row("adviser", "Adviser", "not_requested"),
    row("itso", "ITSO", "not_requested"),
    row("ierc", "IERC", "not_requested"),
    row("ktto", "KTTO", "not_requested"),
    row("rdco", "RDCO Final", "awaiting"),
  ],
  routing_history: [
    {
      group_id: "g-1", from: null, from_label: null, to: ["intake"],
      to_labels: ["Intake & Triage"], actor: "Andrea Lim", reason: "",
      at: "2026-09-18T02:00:00Z",
    },
  ],
});

const afterResubmission = payload({
  workflow_state: "in_review",
  workflow_state_label: "In review",
  current_holders: [
    { party: "ierc", label: "IERC", opened_at: "2026-09-18T03:00:00Z", opened_by: "Test RDCO" },
    { party: "ktto", label: "KTTO", opened_at: "2026-09-18T03:00:00Z", opened_by: "Test RDCO" },
  ],
  parties: [
    row("intake", "Intake", "completed", { outcome: "approved", outcome_label: "Approved", started: true }),
    row("adviser", "Adviser", "not_requested"),
    row("itso", "ITSO", "completed", {
      outcome: "cleared", outcome_label: "Cleared", started: true, preserved: true,
    }),
    row("ierc", "IERC", "active", { outcome: "pending", outcome_label: "Pending", started: true }),
    row("ktto", "KTTO", "active", { outcome: "pending", outcome_label: "Pending" }),
    row("rdco", "RDCO Final", "awaiting"),
  ],
  routing_history: [
    {
      group_id: "g-1", from: null, from_label: null, to: ["intake"],
      to_labels: ["Intake"], actor: "Andrea Lim", reason: "", at: "2026-09-18T02:00:00Z",
    },
    {
      group_id: "g-2", from: "intake", from_label: "Intake", to: ["itso", "ierc", "ktto"],
      to_labels: ["ITSO", "IERC", "KTTO"], actor: "Test RDCO",
      reason: "Needs all three offices.", at: "2026-09-18T03:00:00Z",
    },
  ],
  resubmissions: [
    {
      id: 1, party: "ierc", label: "IERC", state: "resubmitted", state_label: "Resubmitted",
      reason: "Consent form is missing.", requested_by: "Test IERC",
      created_at: "2026-09-18T04:00:00Z", resolved_at: "2026-09-18T05:00:00Z",
    },
  ],
});

const newProposal = payload({
  record_type: "Proposal",
  current_holders: [
    { party: "adviser", label: "Adviser", opened_at: "2026-09-18T02:00:00Z", opened_by: null },
  ],
  parties: [
    row("intake", "Intake", "not_requested"),
    row("adviser", "Adviser", "active"),
    row("itso", "ITSO", "not_requested"),
    row("ierc", "IERC", "not_requested"),
    row("ktto", "KTTO", "not_requested"),
    row("rdco", "RDCO Final", "not_requested"),
  ],
});

beforeEach(() => {
  tracker.mockReset();
});

function renderTracker() {
  return renderScreen(<ReviewRoutingTracker recordId={RECORD_ID} />);
}

async function partyRow(name: RegExp) {
  const table = await screen.findByRole("table", { name: /parties/i });
  return within(table).getByRole("row", { name });
}

describe("ReviewRoutingTracker", () => {
  it("shows a Thesis at intake: Intake active, offices not requested, RDCO awaiting", async () => {
    tracker.mockResolvedValue({ data: thesisAtIntake });
    const { container } = renderTracker();

    expect(await partyRow(/intake & triage/i)).toHaveTextContent(/active/i);
    for (const office of [/^itso/i, /^ierc/i, /^ktto/i]) {
      expect(await partyRow(office)).toHaveTextContent(/not requested/i);
    }
    expect(await partyRow(/rdco/i)).toHaveTextContent(/awaiting/i);
    expect(tracker).toHaveBeenCalledWith(RECORD_ID);

    // The overall state is stated once, as the server words it.
    const region = screen.getByRole("region", { name: /review & routing/i });
    expect(within(region).getByText("Submitted")).toBeInTheDocument();

    await expectNoBlockingA11yViolations(container);
  });

  it("shows a new Proposal as submitted, with RDCO not requested", async () => {
    tracker.mockResolvedValue({ data: newProposal });
    renderTracker();

    expect(await partyRow(/adviser/i)).toHaveTextContent(/active/i);
    expect(await partyRow(/rdco/i)).toHaveTextContent(/not requested/i);
    const region = screen.getByRole("region", { name: /review & routing/i });
    expect(within(region).getByText("Submitted")).toBeInTheDocument();
    expect(within(region).queryByText("Final review")).not.toBeInTheDocument();
  });

  it("shows who holds the record now", async () => {
    tracker.mockResolvedValue({ data: afterResubmission });
    renderTracker();

    const holders = await screen.findByRole("list", { name: /currently with/i });
    expect(within(holders).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "IERC",
      "KTTO",
    ]);
  });

  it("shows a completed office with its outcome, and the preserved badge", async () => {
    tracker.mockResolvedValue({ data: afterResubmission });
    const { container } = renderTracker();

    const itso = await partyRow(/^itso/i);
    expect(itso).toHaveTextContent(/completed/i);
    expect(itso).toHaveTextContent(/cleared/i);
    expect(itso).toHaveTextContent(/preserved/i);

    const ierc = await partyRow(/^ierc/i);
    expect(ierc).toHaveTextContent(/active/i);
    expect(ierc).not.toHaveTextContent(/preserved/i);

    await expectNoBlockingA11yViolations(container);
  });

  it("groups one routing decision to several parties into one line", async () => {
    tracker.mockResolvedValue({ data: afterResubmission });
    renderTracker();

    const history = await screen.findByRole("list", { name: /routing history/i });
    const moves = within(history).getAllByRole("listitem");
    expect(moves).toHaveLength(2);
    expect(moves[0]).toHaveTextContent(/submitted.*intake/i);
    expect(moves[1]).toHaveTextContent("Intake → ITSO + IERC + KTTO");
    expect(moves[1]).toHaveTextContent("Needs all three offices.");
  });

  it("lists the resubmission history", async () => {
    tracker.mockResolvedValue({ data: afterResubmission });
    renderTracker();

    const list = await screen.findByRole("list", { name: /resubmission history/i });
    const [request] = within(list).getAllByRole("listitem");
    expect(request).toHaveTextContent(/ierc/i);
    expect(request).toHaveTextContent(/resubmitted/i);
    expect(request).toHaveTextContent("Consent form is missing.");
  });

  it("says when routing history begins", async () => {
    tracker.mockResolvedValue({ data: thesisAtIntake });
    renderTracker();

    expect(await screen.findByText(/routing recorded from sep 19, 2026/i)).toBeInTheDocument();
  });

  it("says so when the tracker cannot be loaded", async () => {
    tracker.mockRejectedValue(new Error("network"));
    renderTracker();

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load/i);
  });
});
