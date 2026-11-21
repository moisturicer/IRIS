/**
 * The Review & Routing summary in Record details (IR-258; a summary since
 * IR-1264, with the record's status first and its history left to Review).
 *
 * Everything the panel says comes from `GET /records/<id>/tracker/`; nothing is
 * worked out here (workflow_routing_architecture.md §9.1). These cases feed it
 * the payloads the backend's `test_tracker.py` pins for the same situations,
 * and check what a reader of the page -- or a screen reader -- is told.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
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
    not_required: "Not required",
  } as const;
  return {
    party,
    label,
    state,
    state_label: stateLabels[state],
    started: false,
    outcome: null,
    outcome_label: null,
    at: state === "not_requested" || state === "awaiting" || state === "not_required" ? null : "2026-09-18T02:00:00Z",
    preserved: false,
    awaiting_document: false,
    outcome_earlier: false,
    in_pool: false,
    changes_requested: false,
    seats: null,
    carryover: null, carryover_version: null, carryover_label: null,
    due_at: null, original_due_at: null, is_overdue: false, clock_paused: false,
    can_extend: false, extensions: [],
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
    parties: [],
    clearance_strip: [],
    routing_history: [],
    routing_recorded_from: "2026-09-19T12:00:00Z",
    reviews: [],
    versions: [],
    review_comments: [],
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
      reason: "Consent form is missing.", review: 1, version: null, requested_by: "Test IERC",
      created_at: "2026-09-18T04:00:00Z", resolved_at: "2026-09-18T05:00:00Z",
      resolved_by: "Andrea Lim",
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

function renderTracker(props: Partial<Parameters<typeof ReviewRoutingTracker>[0]> = {}) {
  return renderScreen(<ReviewRoutingTracker recordId={RECORD_ID} {...props} />);
}

async function partyRow(name: RegExp) {
  const table = await screen.findByRole("table", { name: /parties/i });
  return within(table).getByRole("row", { name });
}

describe("ReviewRoutingTracker", () => {
  it("announces its loading once, by role and name, and then the table replaces it (IR-939)", async () => {
    tracker.mockReturnValue(new Promise(() => {}));
    renderTracker();

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Loading the review tracker…");
    // One announcement for the panel, not one per skeleton row.
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("drops the loading status when the tracker arrives (IR-939)", async () => {
    tracker.mockResolvedValue({ data: thesisAtIntake });
    renderTracker();

    await screen.findByRole("table", { name: /parties/i });
    expect(screen.queryByText("Loading the review tracker…")).not.toBeInTheDocument();
  });

  it("never shows the retired Intake as a party or as who holds the record (ADR-032 §13)", async () => {
    // A legacy record still stored at Intake: the server sends an active Intake
    // row and an Intake holder. Intake is history, never a step (spec §0, inv. 1).
    tracker.mockResolvedValue({ data: thesisAtIntake });
    const { container } = renderTracker();

    const table = await screen.findByRole("table", { name: /parties/i });
    expect(within(table).queryByRole("row", { name: /intake/i })).not.toBeInTheDocument();
    for (const office of [/^itso/i, /^ierc/i, /^ktto/i]) {
      expect(await partyRow(office)).toHaveTextContent(/not requested/i);
    }
    expect(await partyRow(/rdco/i)).toHaveTextContent(/awaiting/i);
    expect(tracker).toHaveBeenCalledWith(RECORD_ID);
    // Nobody but the retired Intake holds it, so no "Currently with" list.
    expect(screen.queryByRole("list", { name: /currently with/i })).not.toBeInTheDocument();

    await expectNoBlockingA11yViolations(container);
  });

  it("leaves the clearance strip and every history to Review, and links there (IR-1264)", async () => {
    tracker.mockResolvedValue({
      data: {
        ...afterResubmission,
        clearance_strip: [
          { party: "itso", label: "ITSO", kind: "kept", text: "Cleared", note: "Kept from v1", version: 1 },
        ],
      },
    });
    const onOpenHistory = vi.fn();
    const { container } = renderTracker({ onOpenHistory });

    const table = await screen.findByRole("table", { name: /parties/i });
    expect(within(table).queryByRole("row", { name: /intake/i })).not.toBeInTheDocument();
    // One line per party is the summary; the strip would say the same twice.
    expect(screen.queryByRole("list", { name: "Clearances" })).not.toBeInTheDocument();
    for (const history of [/currently with/i, /routing history/i, /resubmission history/i, /document requests/i]) {
      expect(screen.queryByRole("list", { name: history })).not.toBeInTheDocument();
    }
    expect(screen.queryByText("Needs all three offices.")).not.toBeInTheDocument();
    expect(screen.queryByText("Consent form is missing.")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /see review history/i }));
    expect(onOpenHistory).toHaveBeenCalledTimes(1);

    await expectNoBlockingA11yViolations(container);
  });

  it("says no routing is recorded yet when there is no party to show, and still links to Review (IR-1264)", async () => {
    tracker.mockResolvedValue({ data: payload({}) });
    const { container } = renderTracker({ onOpenHistory: vi.fn() });

    expect(await screen.findByText("No routing recorded yet.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /parties/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /see review history/i })).toBeInTheDocument();

    await expectNoBlockingA11yViolations(container);
  });

  it("offers no history link when there is nowhere to send the reader", async () => {
    tracker.mockResolvedValue({ data: afterResubmission });
    renderTracker();

    await screen.findByRole("table", { name: /parties/i });
    expect(screen.queryByRole("button", { name: /see review history/i })).not.toBeInTheDocument();
  });

  it("states the record's status first, once, from what the page gives it (IR-1264)", async () => {
    tracker.mockResolvedValue({ data: newProposal });
    renderTracker({ status: <span>Under review</span> });

    await partyRow(/adviser/i);
    const region = screen.getByRole("region", { name: /review & routing/i });
    expect(within(region).getAllByText("Under review")).toHaveLength(1);
    // The tracker's own copy of the state is not drawn beside it.
    expect(within(region).queryByText("Submitted")).not.toBeInTheDocument();
  });

  it("draws no status line when it is given none", async () => {
    tracker.mockResolvedValue({ data: newProposal });
    renderTracker();

    await partyRow(/adviser/i);
    // The table's own sr-only column header is also "Status"; the line is a span.
    expect(screen.queryByText("Status", { selector: "span" })).not.toBeInTheDocument();
  });

  it("shows a new Proposal with the Adviser active and RDCO not requested", async () => {
    tracker.mockResolvedValue({ data: newProposal });
    renderTracker();

    expect(await partyRow(/adviser/i)).toHaveTextContent(/active/i);
    expect(await partyRow(/rdco/i)).toHaveTextContent(/not requested/i);
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

  it("on the new model: RDCO not required and a pool unassigned; who reviews is Review's (IR-269, IR-1264)", async () => {
    tracker.mockResolvedValue({
      data: payload({
        workflow_state: "in_review",
        workflow_state_label: "In review",
        parties: [
          row("intake", "Intake", "not_requested"),
          row("adviser", "Adviser", "completed", { outcome: "approved", outcome_label: "Approved" }),
          row("itso", "ITSO", "active", {
            outcome: "cleared",
            outcome_label: "Cleared (earlier review) · reviewing again",
            outcome_earlier: true,
            seats: [
              { reviewer_name: "Maria Reyes", state: "in_review", state_label: "In review", verdict: null, verdict_label: null },
              { reviewer_name: "Juan Santos", state: "done", state_label: "Done", verdict: "negative_finding", verdict_label: "Negative finding" },
            ],
          }),
          row("ierc", "IERC", "active", { outcome: "pending", outcome_label: "Pending", in_pool: true, seats: [] }),
          row("ktto", "KTTO", "not_requested"),
          row("rdco", "RDCO", "not_required"),
        ],
      }),
    });
    const { container } = renderTracker();

    const itso = await partyRow(/^itso/i);
    expect(itso).toHaveTextContent("Cleared (earlier review) · reviewing again");
    // Reviewers by name are in Review's Details tab, not repeated in the rail.
    expect(within(itso).queryByRole("list", { name: "Reviewing for ITSO" })).not.toBeInTheDocument();
    expect(itso).not.toHaveTextContent("Maria Reyes");
    expect(await partyRow(/^ierc/i)).toHaveTextContent(/unassigned/i);
    expect(await partyRow(/^rdco/i)).toHaveTextContent("Not required");

    await expectNoBlockingA11yViolations(container);
  });

  it("shows a party with an open revision request as Changes requested, beside its earlier outcome (IR-272)", async () => {
    tracker.mockResolvedValue({
      data: payload({
        workflow_state: "awaiting_resubmission",
        workflow_state_label: "Awaiting resubmission",
        parties: [
          row("adviser", "Adviser", "active", {
            outcome: "declined", outcome_label: "Resubmission requested", changes_requested: true,
          }),
          row("itso", "ITSO", "active", {
            outcome: "cleared",
            outcome_label: "Cleared (earlier review) · reviewing again",
            outcome_earlier: true,
            changes_requested: true,
          }),
          row("ierc", "IERC", "completed", { outcome: "cleared", outcome_label: "Cleared" }),
        ],
      }),
    });
    renderTracker();

    const adviser = await partyRow(/^adviser/i);
    expect(adviser).toHaveTextContent("Changes requested");
    // The request reads once, as Changes requested, not also as the review that made it.
    expect(adviser).not.toHaveTextContent("Resubmission requested");
    const itso = await partyRow(/^itso/i);
    expect(itso).toHaveTextContent("Cleared (earlier review) · reviewing again");
    expect(itso).toHaveTextContent("Changes requested");
    expect(await partyRow(/^ierc/i)).not.toHaveTextContent("Changes requested");
  });

  it("names no reviewer to a viewer who takes no part in the review", async () => {
    tracker.mockResolvedValue({
      data: payload({
        parties: [row("itso", "ITSO", "active", { seats: null })],
      }),
    });
    renderTracker();

    const itso = await partyRow(/^itso/i);
    expect(within(itso).queryByRole("list")).not.toBeInTheDocument();
  });

  it("marks a party waiting on a document (IR-262)", async () => {
    const awaitingDocument = payload({
      ...afterResubmission,
      workflow_state: "awaiting_document",
      workflow_state_label: "Awaiting document",
      parties: afterResubmission.parties.map((p) =>
        p.party === "ierc" ? { ...p, awaiting_document: true } : p,
      ),
      document_requests: [{
        id: 5, party: "ierc", label: "IERC", state: "open", state_label: "Open",
        message: "Rescan the consent form.", requested_by: "Ivy Ethics",
        created_at: "2026-09-20T02:00:00Z", closed_at: null, can_manage: false,
        items: [{
          id: 51, slot: null, label: "Consent form", state: "missing",
          state_label: "Missing", upload: null, uploaded_at: null, rejection_reason: null, decided_at: null,
        }],
      }],
    });
    tracker.mockResolvedValue({ data: awaitingDocument });
    const { container } = renderTracker();

    expect(await partyRow(/^ierc/i)).toHaveTextContent(/awaiting document/i);
    expect(await partyRow(/^ktto/i)).not.toHaveTextContent(/awaiting document/i);
    // The request itself is answered on the Overview and listed in Review.
    expect(screen.queryByText("Rescan the consent form.")).not.toBeInTheDocument();

    await expectNoBlockingA11yViolations(container);
  });

  it("discloses nothing about requests to a viewer who may not read them (IR-349)", async () => {
    const undisclosed = payload({
      ...afterResubmission,
      workflow_state: "awaiting_document",
      workflow_state_label: "Awaiting document",
      parties: afterResubmission.parties.map((p) => ({ ...p, awaiting_document: null })),
      document_requests: null,
    });
    tracker.mockResolvedValue({ data: undisclosed });
    const { container } = renderTracker();

    for (const party of [/^ierc/i, /^ktto/i, /^itso/i]) {
      const row = await partyRow(party);
      expect(row).not.toHaveTextContent(/awaiting document/i);
      expect(row).not.toHaveTextContent("◐");
    }
    expect(screen.queryByRole("list", { name: /document requests/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /document requests/i })).not.toBeInTheDocument();

    await expectNoBlockingA11yViolations(container);
  });

  it("says so when the tracker cannot be loaded", async () => {
    tracker.mockRejectedValue(new Error("network"));
    renderTracker();

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load/i);
  });

  it("offers Try again rather than telling the reader to reload (IR-906)", async () => {
    tracker.mockRejectedValueOnce(new Error("network")).mockResolvedValue({ data: payload({}) });
    renderTracker();

    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(tracker).toHaveBeenCalledTimes(2);
  });

  it("says a timed-out tracker took too long, and Retry reads it again (IR-906)", async () => {
    tracker.mockRejectedValueOnce(new RequestTimeoutError(30_000, "get", "/records/12/tracker/")).mockResolvedValue({ data: payload({}) });
    renderTracker();

    expect(await screen.findByRole("alert")).toHaveTextContent("The review tracker took too long to load.");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(tracker).toHaveBeenCalledTimes(2));
  });
});
