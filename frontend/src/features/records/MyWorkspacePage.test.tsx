/**
 * My Workspace reads a case's place from the API (IR-259, ADR-021 §4).
 *
 * Each case card's stage, holding office and "Action Required" flag come from
 * `workflow_state` and `current_holders`, never from the stored stage values
 * IR-260 retires. Every row below is one state a record can be in today,
 * carrying what the API actually sends for it (`apps/reviews/shadow.py`
 * `active_parties_for`, `apps/reviews/tracker.py` `derive_workflow_state`),
 * and the card text the page showed for that state before this change.
 *
 * **Two labels deliberately change.** The office line now shows the party
 * label the API serves (`tracker.party_label`) instead of a client-side
 * role name: a record held by Intake reads "Intake" to its owner, not "RDCO"
 * (ADR-021 §2, accepted on IR-259), and RDCO's final-review party reads
 * "RDCO Final", matching the Review & Routing Tracker on the same record.
 *
 * **`pipeline_status` is `in_review` on every in-review row.** That is the
 * value IR-260 stores in place of the five stage values; a card that still
 * read the stage values would put all of these rows in Validation.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { Party, RecordClearance, RecordDetail, TrackerHolder, WorkflowState } from "@/types/records";

import MyWorkspacePage from "./MyWorkspacePage";

const base: RecordDetail = {
  id: 1,
  title: "Untitled",
  abstract: "",
  year_accomplished: 2026,
  year_completed: null,
  abstract_file: null,
  classification_name: "Applied Research",
  classification: "Applied Research",
  psced: null,
  record_type_name: "Thesis/Research",
  record_type: "Thesis/Research",
  pipeline_status: "in_review",
  is_ip: false,
  ip_type: "",
  for_commercialization: false,
  community_extension: false,
  access_count: 0,
  file_count: 0,
  created_at: "2026-09-01T08:00:00Z",
  authors: [],
  adviser: null,
  added_by: null,
  requires_ethics_review: false,
  requested_itso: false,
  requested_ierc: false,
  requested_ktto: false,
  owners: [],
  is_deleted: false,
  reviews: [],
  clearances: [],
  resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
  stage_label: "",
  your_office: null,
  your_office_label: null,
  files: [],
  workflow_state: "in_review",
  workflow_state_label: "In review",
  current_holders: [],
  can_act: [],
};

/** The student-facing holder labels the API serves (ADR-021 §2). */
const HOLDER_LABEL: Record<Party, string> = {
  intake: "Intake",
  adviser: "Adviser",
  itso: "ITSO",
  ierc: "IERC",
  ktto: "KTTO",
  rdco: "RDCO Final",
};

function holders(...parties: Party[]): TrackerHolder[] {
  return parties.map((party) => ({
    party,
    label: HOLDER_LABEL[party],
    opened_at: "2026-09-02T08:00:00Z",
    opened_by: null,
  }));
}

function clearance(office: RecordClearance["office"], status: RecordClearance["status"]): RecordClearance {
  return {
    office,
    office_label: office.toUpperCase(),
    status,
    status_label: status,
    comment: "",
    reviewed_by_name: null,
    updated_at: "2026-09-03T08:00:00Z",
    preserved: false,
  };
}

interface Case {
  /** The stored status this row stood for before IR-260. */
  was: string;
  record: Partial<RecordDetail> & { workflow_state: WorkflowState };
  /** The card's stage line, as it read before this change. */
  current: string;
  office: string;
  actionRequired?: boolean;
}

const CASES: Case[] = [
  {
    was: "draft",
    record: { pipeline_status: "draft", workflow_state: "draft" },
    current: "Current: Validation",
    office: "—",
  },
  {
    was: "rdco_intake, not yet triaged",
    record: { workflow_state: "submitted", current_holders: holders("intake") },
    current: "Current: Review & Routing",
    office: "Intake",
  },
  {
    was: "adviser_review, not yet opened",
    record: {
      record_type_name: "Proposal",
      workflow_state: "submitted",
      current_holders: holders("adviser"),
    },
    current: "Current: Review & Routing",
    office: "Adviser",
  },
  {
    // The Adviser both receives and decides a Proposal, so once they have
    // acted the API says final_review. The card never showed it as such.
    was: "adviser_review, after the Adviser has acted",
    record: {
      record_type_name: "Proposal",
      workflow_state: "final_review",
      current_holders: holders("adviser"),
    },
    current: "Current: Review & Routing",
    office: "Adviser",
  },
  {
    was: "itso_review",
    record: {
      workflow_state: "in_review",
      current_holders: holders("ierc", "itso"),
      clearances: [clearance("ierc", "pending"), clearance("itso", "pending")],
    },
    current: "Current: Office Review",
    office: "IERC + ITSO",
  },
  {
    was: "parallel_review",
    record: {
      workflow_state: "in_review",
      current_holders: holders("ktto"),
      clearances: [clearance("itso", "cleared"), clearance("ktto", "pending")],
    },
    current: "Current: Office Review",
    office: "KTTO",
  },
  {
    was: "rdco_review",
    record: {
      workflow_state: "final_review",
      current_holders: holders("rdco"),
      clearances: [clearance("itso", "cleared")],
    },
    current: "Current: Final Review",
    office: "RDCO Final",
  },
  {
    was: "declined at intake",
    record: { workflow_state: "awaiting_resubmission", current_holders: holders("intake") },
    current: "Awaiting your revision",
    office: "—",
    actionRequired: true,
  },
  {
    // ITSO asked for changes; IERC has not finished. Only IERC is still
    // working -- ITSO is waiting on the author, as the card always said.
    was: "declined by ITSO while IERC is pending",
    record: {
      workflow_state: "awaiting_resubmission",
      current_holders: holders("ierc", "itso"),
      clearances: [clearance("ierc", "pending"), clearance("itso", "declined")],
    },
    current: "Awaiting your revision",
    office: "IERC",
    actionRequired: true,
  },
  {
    was: "approved",
    record: { pipeline_status: "approved", workflow_state: "approved", record_type_name: "Proposal" },
    current: "Current: Research Ongoing",
    office: "—",
  },
  {
    was: "completed",
    record: { pipeline_status: "completed", workflow_state: "completed", record_type_name: "Proposal" },
    current: "Current: Completed",
    office: "—",
  },
  {
    was: "published",
    record: { pipeline_status: "published", workflow_state: "published" },
    current: "Current: Completed",
    office: "—",
  },
  {
    was: "rejected",
    record: { pipeline_status: "rejected", workflow_state: "rejected" },
    current: "Current: Rejected",
    office: "—",
  },
  {
    // A published record whose owner asked RDCO to delete it. Still readable
    // to its owner; filed with Rejected, as the page always has.
    was: "pending_delete",
    record: { pipeline_status: "pending_delete", workflow_state: "pending_delete" },
    current: "Current: Rejected",
    office: "—",
  },
];

let shownRecords: RecordDetail[] = [];

vi.mock("@/api/records", () => ({
  recordsApi: {
    mine: vi.fn(() => Promise.resolve({ data: shownRecords })),
  },
}));

function recordFor(c: Case, id: number): RecordDetail {
  return { ...base, id, title: `Case ${id}: ${c.was}`, ...c.record };
}

/** The card's whole "Office: … · Submitted: …" line, anchored so "IERC" cannot match "IERC + ITSO". */
function officeLine(office: string): RegExp {
  const escaped = office.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`^Office: ${escaped}\\s*·`);
}

async function findCard(title: string) {
  return screen.findByRole("article", { name: title });
}

beforeEach(() => {
  shownRecords = [];
});

describe("a My Workspace case card", () => {
  it.each(CASES.map((c, i) => [c.was, c, i + 1] as const))(
    "reads its place from the API when it was %s",
    async (_was, c, id) => {
      const record = recordFor(c, id);
      shownRecords = [record];
      renderScreen(<MyWorkspacePage />);

      const card = within(await findCard(record.title));
      expect(card.getByText(c.current)).toBeInTheDocument();
      // The "Office:" line only -- the pending-office pills repeat office names.
      const line = officeLine(c.office);
      // getByText reads an element's own text; the office name is in a child span.
      expect(card.getByText((_, el) => el?.tagName === "P" && line.test(el.textContent ?? ""))).toBeInTheDocument();
      if (c.actionRequired) {
        expect(card.getByText("Action Required")).toBeInTheDocument();
      } else {
        expect(card.queryByText("Action Required")).not.toBeInTheDocument();
      }
    },
  );

  it("files every case under the tab its API state belongs to", async () => {
    shownRecords = CASES.map((c, i) => recordFor(c, i + 1));
    renderScreen(<MyWorkspacePage />);
    await findCard(shownRecords[0].title);

    await userEvent.click(screen.getByRole("button", { name: "Review & Routing" }));
    expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual([
      "Case 2: rdco_intake, not yet triaged",
      "Case 3: adviser_review, not yet opened",
      "Case 4: adviser_review, after the Adviser has acted",
    ]);
  });

  it("has no serious or critical accessibility violations", async () => {
    shownRecords = CASES.map((c, i) => recordFor(c, i + 1));
    const { container } = renderScreen(<MyWorkspacePage />);
    await findCard(shownRecords[0].title);

    await expectNoBlockingA11yViolations(container);
  });
});
