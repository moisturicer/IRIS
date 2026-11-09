/**
 * The Changes tab in the reviewer's workspace (IR-873): offered only with two
 * Versions or more, *Show in paper* opens the right Version and lands the
 * reader on the change's page, and a thread link opens the thread.
 *
 * The reader is a stand-in that reads the same context the PDF reader does
 * (as in ThreadsWorkspace.test.tsx).
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Capability } from "@/features/records/capabilities";
import { renderScreen, screen, waitFor } from "@/test/render";
import type { RecordDetail, VersionComparisonPayload } from "@/types/records";

import { ReviewWorkspace } from "../ReviewWorkspace";
import { useReaderAnnotations } from "../threads/readerAnnotations";
import { comment } from "../threads/threadFixtures";

const api = vi.hoisted(() => ({
  tracker: vi.fn(),
  documentRequestSlots: vi.fn(() => new Promise(() => {})),
  reviewComments: vi.fn(),
  compareVersions: vi.fn(),
}));
vi.mock("@/api/records", () => ({ recordsApi: api }));

const TRACKER = {
  record_id: 7, record_type: "Thesis / Research", workflow_state: "in_review", workflow_state_label: "In review",
  current_holders: [], parties: [], routing_history: [], routing_recorded_from: null, reviews: [], versions: [],
  review_comments: [], review_rounds: [], resubmissions: [], document_requests: [], clearances: [],
  resubmission: { policy: "clearance_aware", required_parties: [] }, reassignments: [], assignment_deadline_history: [],
};

const REGION = { page: 4, left: 0.1, top: 0.3, right: 0.9, bottom: 0.34 };
const COMPARISON: VersionComparisonPayload = {
  state: "ready", message: null, from: 1, to: 2, mode: "sections", changes: [], notices: [], documents: [],
  counts: { changed: 0, added: 0, removed: 1, moved: 0, sections_renamed: 0, sections_moved: 0 },
  sections: [{
    status: "changed", renamed: false, moved: false,
    from: { key: "method", heading: "Method", page: 4 }, to: { key: "method", heading: "Method", page: 4 },
    counts: { changed: 0, added: 0, removed: 1, moved: 0 },
    changes: [{ kind: "removed", certainty: "established", to: null,
      from: { section: "method", text: "A sample of 40.", page: 4, regions: [REGION] } }],
  }],
  threads: [{ thread: 1, side: "from", page: 4, section: 0 }],
};

const record = (versions: number) => ({
  id: 7, title: "Flood-Risk Mapping", can_request_document: [], current_holders: [], files: [], keywords: [],
  abstract_file: null, review_claim: null, revision: null,
  readiness: { verdict: "ready", headline: "Ready to finish.", items: [] },
  my_seats: [{ id: 1, party: "itso", state: "in_review", assignment: 3, verdict_label: null, state_label: "Reviewing" }],
  versions: Array.from({ length: versions }, (_, i) => ({ number: i + 1, cause_label: "Submitted", manuscript_url: "/m" })),
  routing: { send_to_rdco: false, send_to_rdco_blocked: null, route_as: null, targets: [] },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
}) as unknown as RecordDetail;

function StandInReader() {
  const a = useReaderAnnotations();
  return <p>{a?.landing ? `Landed on page ${a.landing.page}` : "Not landed"}</p>;
}

function openWorkspace(versions: number) {
  const onShowVersion = vi.fn();
  renderScreen(
    <ReviewWorkspace record={record(versions)} can={new Set<Capability>(["comment_review"])} reader={<StandInReader />}
      timelineVersion={0} onChanged={() => {}} documents={null} documentsOpen={false} onDocuments={() => {}}
      onShowVersion={onShowVersion} />,
  );
  return { onShowVersion };
}

beforeEach(() => {
  api.tracker.mockReset().mockResolvedValue({ data: TRACKER });
  api.reviewComments.mockReset().mockResolvedValue({ data: [
    comment({ id: 1, party: "itso", party_label: "ITSO", severity: "must_fix",
      anchor: { version: 1, page: 4, quote: "A sample of 40.", regions: [REGION] } }),
  ] });
  api.compareVersions.mockReset().mockResolvedValue({ data: COMPARISON });
});

describe("the Changes tab in the review workspace", () => {
  it("is offered only when there are two Versions to compare", async () => {
    openWorkspace(1);
    await screen.findByRole("tab", { name: /Threads/ });
    expect(screen.queryByRole("tab", { name: "Changes" })).toBeNull();
    expect(api.compareVersions).not.toHaveBeenCalled();
  });

  it("asks for the comparison only once opened", async () => {
    const user = userEvent.setup();
    openWorkspace(2);
    const tab = await screen.findByRole("tab", { name: "Changes" });
    expect(api.compareVersions).not.toHaveBeenCalled();
    await user.click(tab);
    expect(await screen.findByRole("article", { name: "Removed, page 4" })).toBeInTheDocument();
  });

  it("opens the earlier Version and lands on the change's page", async () => {
    const user = userEvent.setup();
    const { onShowVersion } = openWorkspace(2);
    await user.click(await screen.findByRole("tab", { name: "Changes" }));
    await user.click(await screen.findByRole("button", { name: "Show in v1, p. 4" }));
    expect(onShowVersion).toHaveBeenCalledWith(1);
    expect(screen.getByText("Landed on page 4")).toBeInTheDocument();
  });

  it("opens a thread listed under its section in the Threads tab", async () => {
    const user = userEvent.setup();
    openWorkspace(2);
    await user.click(await screen.findByRole("tab", { name: "Changes" }));
    await user.click(await screen.findByRole("button", { name: /^Thread 1 · ITSO, Must fix/ }));
    expect(screen.getByRole("tab", { name: /Threads/ })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(screen.getByRole("article", { name: "Thread 1, ITSO" })).toHaveFocus());
  });
});
