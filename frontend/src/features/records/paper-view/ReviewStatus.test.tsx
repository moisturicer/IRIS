/**
 * Where the review stands, at the top of the Review section (IR-624): whose
 * turn it is, each party's reviewers, state and due date, and -- the thesis
 * contribution -- which clearances the latest version kept and which it
 * reset, with the version each applies to.
 *
 * The fixture is a two-office record through one revision cycle: ITSO
 * cleared v1, IERC asked for changes, the owner submitted v2. Preserved and
 * reset are the server's (`carryover`); these tests give the client nothing
 * to infer them from, so a rendering that worked either out would fail.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { RecordTracker, TrackerPartyRow } from "@/types/records";

import { recordsApi } from "@/api/records";

import { ReviewTimeline } from "./ReviewTimeline";

vi.mock("@/api/records", () => ({ recordsApi: { tracker: vi.fn() } }));

const tracker = vi.mocked(recordsApi.tracker);

function row(overrides: Partial<TrackerPartyRow> & Pick<TrackerPartyRow, "party" | "label">): TrackerPartyRow {
  return {
    state: "completed", state_label: "Completed", started: false,
    outcome: null, outcome_label: null, at: "2026-10-01T02:00:00Z",
    preserved: false, carryover: null, carryover_version: null, carryover_label: null,
    awaiting_document: false, outcome_earlier: false, in_pool: false, changes_requested: false,
    seats: null,
    due_at: null, original_due_at: null, is_overdue: false, clock_paused: false,
    can_extend: false, extensions: [],
    ...overrides,
  };
}

/** ITSO cleared v1 and was kept; IERC asked, and v2 reset it. */
function afterRevision(): RecordTracker {
  return {
    record_id: 7,
    record_type: "Thesis / Research",
    workflow_state: "in_review",
    workflow_state_label: "In review",
    current_holders: [{ party: "ierc", label: "IERC", opened_at: "2026-10-02T02:00:00Z", opened_by: null }],
    parties: [
      row({
        party: "adviser", label: "Adviser", outcome: "approved", outcome_label: "Approved",
        seats: [{ reviewer_name: "Dana Reyes", state: "done", state_label: "Done", verdict: "approved", verdict_label: "Approved" }],
      }),
      row({
        party: "itso", label: "ITSO", outcome: "cleared", outcome_label: "Cleared",
        preserved: true, carryover: "preserved", carryover_version: 1,
        carryover_label: "Cleared on v1, preserved",
        seats: [{ reviewer_name: "Mara Santos", state: "done", state_label: "Done", verdict: "approved", verdict_label: "Cleared" }],
      }),
      row({
        party: "ierc", label: "IERC", state: "active", state_label: "Active", started: true,
        outcome: "pending", outcome_label: "Pending",
        carryover: "reset", carryover_version: 2, carryover_label: "Reset by v2",
        due_at: "2026-11-04T15:59:00Z", original_due_at: "2026-11-04T15:59:00Z",
        seats: [
          { reviewer_name: "Leo Tan", state: "in_review", state_label: "In review", verdict: null, verdict_label: null },
          { reviewer_name: "Ana Cruz", state: "done", state_label: "Done", verdict: "approved", verdict_label: "Cleared" },
        ],
      }),
      row({ party: "ktto", label: "KTTO", state: "not_requested", state_label: "Not requested", at: null }),
      row({ party: "rdco", label: "RDCO", state: "awaiting", state_label: "Awaiting", at: null }),
    ],
    routing_history: [],
    routing_recorded_from: null,
    reviews: [],
    versions: [],
    review_comments: [],
    resubmissions: [],
    document_requests: [],
    clearances: [],
    resubmission: { count: 1, last_resubmitted_at: "2026-10-02T01:00:00Z", declining_office: "ierc", offices_preserved: ["itso"] },
  };
}

function respond(data: RecordTracker) {
  tracker.mockResolvedValue({ data } as Awaited<ReturnType<typeof recordsApi.tracker>>);
}

async function parties() {
  return screen.findByRole("list", { name: "Where each party stands" });
}

function partyItem(list: HTMLElement, label: string) {
  return within(list).getAllByRole("listitem").find((li) => li.firstElementChild?.textContent === label)!;
}

describe("Where the review stands", () => {
  beforeEach(() => vi.clearAllMocks());

  it("marks the cleared office preserved and the asking office reset, with each version", async () => {
    respond(afterRevision());
    const { container } = renderScreen(<ReviewTimeline recordId={7} />);

    const list = await parties();
    expect(partyItem(list, "ITSO")).toHaveTextContent("Cleared on v1, preserved");
    expect(partyItem(list, "IERC")).toHaveTextContent("Reset by v2");
    // Nothing is said of an office the version left alone.
    expect(partyItem(list, "Adviser")).not.toHaveTextContent(/preserved|reset/i);
    await expectNoBlockingA11yViolations(container);
  });

  it("states whose turn it is in one line", async () => {
    respond(afterRevision());
    renderScreen(<ReviewTimeline recordId={7} />);

    expect(await screen.findByText("Waiting on IERC: 1 of 2 seats done")).toBeInTheDocument();
  });

  it("names each office's reviewers, their state, and the due date in words", async () => {
    respond(afterRevision());
    renderScreen(<ReviewTimeline recordId={7} />);

    const ierc = partyItem(await parties(), "IERC");
    const seats = within(ierc).getByRole("list", { name: "Reviewing for IERC" });
    expect(within(seats).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Leo Tan — in review",
      "Ana Cruz — done · Cleared",
    ]);
    expect(ierc).toHaveTextContent("Due Nov 4, 2026");
  });

  it("lists only the parties that were asked", async () => {
    respond(afterRevision());
    renderScreen(<ReviewTimeline recordId={7} />);

    const labels = within(await parties())
      .getAllByRole("listitem")
      .map((li) => li.firstElementChild?.textContent)
      .filter((l) => ["Adviser", "ITSO", "IERC", "KTTO", "RDCO"].includes(l ?? ""));
    expect(labels).toEqual(["Adviser", "ITSO", "IERC", "RDCO"]);
  });

  it("says a due date is overdue, paused or extended in words, not colour", async () => {
    const data = afterRevision();
    const ierc = data.parties[2];
    data.parties[2] = { ...ierc, is_overdue: true, due_at: "2026-10-20T15:59:00Z", original_due_at: "2026-10-20T15:59:00Z" };
    respond(data);
    const { unmount } = renderScreen(<ReviewTimeline recordId={7} />);
    expect(partyItem(await parties(), "IERC")).toHaveTextContent("Overdue: was due Oct 20, 2026");
    unmount();

    data.parties[2] = { ...ierc, clock_paused: true };
    respond(data);
    renderScreen(<ReviewTimeline recordId={7} />);
    expect(partyItem(await parties(), "IERC")).toHaveTextContent("Clock paused while waiting on the submitter");
  });

  it("names the original date when a due date was extended", async () => {
    const data = afterRevision();
    data.parties[2] = { ...data.parties[2], original_due_at: "2026-10-30T15:59:00Z" };
    respond(data);
    renderScreen(<ReviewTimeline recordId={7} />);

    expect(partyItem(await parties(), "IERC")).toHaveTextContent("Due Nov 4, 2026, extended from Oct 30, 2026");
  });

  it("shows no reviewer to a viewer the server does not tell, and still what was kept", async () => {
    // The server withholds seats and reviews from a viewer who may not read
    // the review (IR-479); preserved and reset are outcomes, and still come.
    const data = afterRevision();
    data.parties = data.parties.map((p) => ({ ...p, seats: null }));
    data.reviews = null;
    respond(data);
    const { container } = renderScreen(<ReviewTimeline recordId={7} />);

    const list = await parties();
    expect(within(list).queryByRole("list", { name: /^Reviewing for/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Leo Tan|Mara Santos|Dana Reyes/)).not.toBeInTheDocument();
    expect(partyItem(list, "ITSO")).toHaveTextContent("Cleared on v1, preserved");
    expect(screen.getByText("Waiting on IERC")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("leaves the turn to the server's words while the submitter holds the record", async () => {
    const data = afterRevision();
    data.workflow_state = "awaiting_resubmission";
    data.workflow_state_label = "Awaiting resubmission";
    respond(data);
    renderScreen(<ReviewTimeline recordId={7} />);

    expect(await screen.findByText("Waiting on the submitter: Awaiting resubmission")).toBeInTheDocument();
  });
});
