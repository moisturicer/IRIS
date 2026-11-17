/**
 * The author's review actions sit in the review pane's foot (IR-1206).
 *
 * Until IR-1206 the author's Review had its own layout, whose action bar
 * stuck over the bottom of the reader below `reading-wide`, so the reader
 * took the bar's measured height as a bottom inset (IR-477). The author now
 * has the reviewers' frame: the bar is in the pane, beside the reader or in
 * its drawer, never over the paper, so there is no inset to give. These
 * tests replace IR-477's, deliberately.
 */
import { describe, expect, it, vi } from "vitest";

import { renderScreen, screen, within } from "@/test/render";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

import { ReviewWorkspace } from "./ReviewWorkspace";

vi.mock("@/api/records", () => ({
  recordsApi: {
    tracker: vi.fn(() => new Promise(() => {})),
    documentRequestSlots: vi.fn(() => new Promise(() => {})),
  },
}));

const record = {
  id: 7,
  title: "Groundwater Recharge Mapping in Metro Cebu",
  workflow_state: "in_review",
  workflow_state_label: "In review",
  can_request_document: ["ierc"],
  current_holders: [],
  my_seats: [],
  versions: [],
  readiness: null,
  routing: { send_to_rdco: false, route_as: null, targets: [] },
} as unknown as RecordDetail;

function openReviewTab(granted: Capability[]) {
  return renderScreen(
    <ReviewWorkspace
      record={record}
      authorView
      can={new Set(granted)}
      reader={<div>The paper</div>}
      timelineVersion={0}
      onChanged={() => {}}
      documents={<p>Every document</p>}
    />,
  );
}

describe("the author's review actions (IR-1206)", () => {
  it("sit in the review pane's foot when the server grants one", async () => {
    openReviewTab(["request_document"]);

    const pane = screen.getByRole("region", { name: "Review pane" });
    const foot = within(pane).getByRole("contentinfo", { name: "Your actions" });
    expect(await within(foot).findByRole("toolbar", { name: "Review actions" })).toBeInTheDocument();
  });

  it("leave no foot at all when none is granted", () => {
    openReviewTab([]);

    expect(screen.queryByRole("contentinfo", { name: "Your actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("toolbar", { name: "Review actions" })).not.toBeInTheDocument();
  });

  it("never show the reviewers' Your part footer or the tour", () => {
    openReviewTab([]);

    expect(screen.queryByRole("contentinfo", { name: "Your part" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /tour/i })).not.toBeInTheDocument();
  });
});
