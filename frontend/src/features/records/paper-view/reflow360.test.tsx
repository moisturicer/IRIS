/**
 * Paper View's Overview reflows at 360 CSS px (IR-921; WCAG 1.4.10).
 *
 * jsdom has no layout, so it cannot measure a horizontal scrollbar. The real
 * check is the Core journeys' `a11y.reflow360` (e2e/support/a11y.ts), which
 * screens 01 and 05 run in a browser. What these cases hold is the cause that
 * check found: three rows that could not shrink below their content, because a
 * native select is as wide as its longest option and a flex or table child
 * defaults to `min-width: auto`. Each is asserted by what it lets the row do,
 * not by a class it happens to use for it elsewhere.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, within } from "@/test/render";
import type { RecordDetail, RecordTracker, RecordVersion, TrackerPartyRow } from "@/types/records";

import { PaperGovernance } from "./PaperGovernance";
import { ReviewRoutingTracker } from "./ReviewRoutingTracker";
import { VersionPicker } from "./VersionPicker";

const tracker = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: { tracker: (id: number) => tracker(id) },
}));

const LONG = "Dr.Maria-Concepcion-Villanueva-Santos-Hernandez@institution.example.edu";

const versions: RecordVersion[] = [
  { number: 1, cause: "submission", cause_label: "Submission", created_at: "2026-11-01T01:00:00Z", created_by_name: null, manuscript_url: "/a.pdf" },
  { number: 2, cause: "revision", cause_label: "Revision after review", created_at: "2026-11-05T01:00:00Z", created_by_name: null, manuscript_url: "/b.pdf" },
];

describe("the version picker", () => {
  it("can shrink below its longest option, so a phone never scrolls sideways", () => {
    renderScreen(<VersionPicker versions={versions} viewing={null} onChoose={() => {}} />);
    const select = screen.getByRole("combobox", { name: "Version" });
    expect(select.className).toMatch(/\bmin-w-0\b/);
    expect(select.className).toMatch(/\bmax-w-full\b/);
    expect(select.parentElement!.className).toMatch(/\bmin-w-0\b/);
  });

  it("keeps the compact reading-header picker at its fixed width", () => {
    renderScreen(<VersionPicker compact versions={versions} viewing={null} onChoose={() => {}} />);
    const select = screen.getByRole("combobox", { name: "Version" });
    expect(select.className).toMatch(/\bw-24\b/);
    expect(select.parentElement!.className).toMatch(/\bshrink-0\b/);
  });
});

describe("the governance ledger", () => {
  it("lets a long value wrap inside its row", () => {
    const record = {
      classification_name: LONG,
      record_type_name: "Thesis / Research",
      year_accomplished: 2026,
      is_ip: false,
      ip_type: null,
      ip_release: null,
      for_commercialization: false,
    } as unknown as RecordDetail;
    renderScreen(<PaperGovernance record={record} />);
    const value = screen.getByText(LONG);
    expect(value.tagName).toBe("DD");
    expect(value.className).toMatch(/\bmin-w-0\b/);
    expect(value.className).toContain("[overflow-wrap:anywhere]");
  });
});

describe("the routing tracker", () => {
  beforeEach(() => tracker.mockReset());

  it("lets a reviewer's long name wrap in the seat list, not widen the table", async () => {
    const party = {
      party: "ierc", label: "IERC", state: "active", state_label: "Active", started: true,
      outcome: null, outcome_label: null, at: "2026-11-05T01:00:00Z", preserved: false,
      awaiting_document: false, outcome_earlier: false, in_pool: false, changes_requested: false,
      carryover: null, carryover_version: null, carryover_label: null,
      due_at: null, original_due_at: null, is_overdue: false, clock_paused: false, can_extend: false, extensions: [],
      seats: [{ reviewer_name: LONG, state: "in_review", state_label: "Reviewing", verdict: null, verdict_label: null }],
    } as TrackerPartyRow;
    tracker.mockResolvedValue({
      data: {
        record_id: 15, record_type: "Thesis / Research", workflow_state: "submitted", workflow_state_label: "Submitted",
        current_holders: [], parties: [party], routing_history: [], routing_recorded_from: null, reviews: [],
        versions: [], review_comments: [], resubmissions: [], document_requests: [], clearances: [],
        resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
      } satisfies RecordTracker,
    });
    renderScreen(<ReviewRoutingTracker recordId={15} />);

    const seats = await screen.findByRole("list", { name: "Reviewing for IERC" });
    expect(within(seats).getByText(new RegExp(LONG))).toBeInTheDocument();
    expect(seats.className).toContain("[overflow-wrap:anywhere]");
    // Not table-wide: that would let the party and status columns break inside
    // a word on a wide screen, where nothing overflows.
    expect(seats.closest("table")!.className).not.toContain("overflow-wrap");
  });
});
