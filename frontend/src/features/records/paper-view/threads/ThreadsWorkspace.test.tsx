/**
 * Threads in the reviewer's workspace (IR-875): the reader's Comment opens
 * the composer in the Threads tab, a pin opens its thread, Readiness's
 * `show_threads` shows a party's threads, the tab counts what is open, and
 * the footer finishes the review instead of offering each verdict apart.
 *
 * The reader is a stand-in that reads the same context the PDF reader does,
 * so the wiring is tested without pdf.js; the PDF reader's own use of it is
 * `passage`'s and `readerAnnotations`' to answer for.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Capability } from "@/features/records/capabilities";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { RecordDetail, ReviewComment } from "@/types/records";

import { ReviewWorkspace } from "../ReviewWorkspace";
import { useReaderAnnotations } from "./readerAnnotations";
import { comment } from "./threadFixtures";

const api = vi.hoisted(() => ({
  tracker: vi.fn(),
  documentRequestSlots: vi.fn(() => new Promise(() => {})),
  reviewComments: vi.fn(),
  finishReview: vi.fn(),
  responseLetters: vi.fn(),
}));
vi.mock("@/api/records", () => ({ recordsApi: api }));

const THREADS: ReviewComment[] = [
  comment({ id: 1, party: "itso", party_label: "ITSO", severity: "must_fix",
    anchor: { version: 2, page: 4, quote: "a sample of 40", regions: [{ page: 4, left: 0.1, top: 0.3, right: 0.4, bottom: 0.32 }] } }),
  comment({ id: 2, party: "adviser", party_label: "Adviser", severity: "suggestion" }),
  comment({ id: 3, party: "itso", party_label: "ITSO", is_draft: true, can_delete: true }),
];

const TRACKER = {
  record_id: 7, record_type: "Thesis / Research", workflow_state: "in_review", workflow_state_label: "In review",
  current_holders: [], parties: [], routing_history: [], routing_recorded_from: null, reviews: [], versions: [],
  review_comments: [], review_rounds: [], resubmissions: [], document_requests: [], clearances: [],
  resubmission: { policy: "clearance_aware", required_parties: [] }, reassignments: [], assignment_deadline_history: [],
};

beforeEach(() => {
  api.tracker.mockReset().mockResolvedValue({ data: TRACKER });
  api.reviewComments.mockReset().mockResolvedValue({ data: THREADS });
  api.finishReview.mockReset().mockResolvedValue({ data: {} });
  api.responseLetters.mockReset().mockResolvedValue({ data: [] });
});

const LETTER = (version: number) => ({
  version, created_at: "2026-11-09T00:00:00Z",
  entries: [{ thread: 1, party: "itso", party_label: "ITSO", severity: "must_fix", comment: "Name the sample.",
    version: 1, page: 4, quote: "a sample of 40", answer: "addressed", note: "Section 3.2 names it." }],
});

const record = {
  id: 7,
  title: "Flood-Risk Mapping",
  can_request_document: [],
  current_holders: [],
  files: [],
  keywords: [],
  abstract_file: null,
  my_seats: [{ id: 1, party: "itso", state: "in_review", assignment: 3, verdict_label: null, state_label: "Reviewing" }],
  versions: [{ number: 1 }, { number: 2 }],
  review_claim: null,
  routing: { send_to_rdco: false, send_to_rdco_blocked: null, route_as: null, targets: [] },
  revision: { party: "itso", label: "ITSO", blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  office_review: { party: "itso", label: "ITSO", blocked: null, clear_blocked: "ITSO has 1 open Must fix thread.", assignment: 3 },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
  readiness: {
    verdict: "blocked", headline: "Resolve ITSO's Must fix threads before clearing.",
    items: [{ kind: "open_thread", severity: "blocker", label: "ITSO has 1 open Must fix thread.", party: "itso",
      actor_name: null, since: null, paused: null, action: { kind: "show_threads", target: "itso" } }],
  },
} as unknown as RecordDetail;

/** Reads the reader context as the PDF reader does: pins, and a Comment on a fixed passage. */
function StandInReader() {
  const a = useReaderAnnotations();
  return (
    <div>
      {a?.marks.filter((m) => m.version === a.currentVersion).map((m) => (
        <button key={m.key} type="button" onClick={m.onActivate} aria-label={m.label}>{m.pin}</button>
      ))}
      {a?.onComment && (
        <button type="button" onClick={() => a.onComment?.({
          page: 6, quote: "ultrasonic sensors", prefix: "", suffix: "", regions: [],
        }, 2)}>Comment</button>
      )}
    </div>
  );
}

function openWorkspace(caps: Capability[] = ["comment_review", "finish_review", "office_review", "request_revision"]) {
  return renderScreen(
    <ReviewWorkspace record={record} can={new Set(caps)} reader={<StandInReader />} timelineVersion={0}
      onChanged={() => {}} documents={null} documentsOpen={false} onDocuments={() => {}} />,
  );
}

describe("threads in the review workspace", () => {
  it("counts the open threads on the Threads tab", async () => {
    openWorkspace();
    expect(await screen.findByRole("tab", { name: "Threads 1 must fix · 1 suggestion" })).toBeInTheDocument();
  });

  it("opens the composer in Threads from the reader's Comment, on the passage", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(await screen.findByRole("button", { name: "Comment" }));
    expect(screen.getByRole("tab", { name: /Threads/ })).toHaveAttribute("aria-selected", "true");
    const form = within(screen.getByRole("form", { name: "New comment" }));
    expect(form.getByText("“ultrasonic sensors”")).toBeInTheDocument();
    expect(form.getByRole("radio", { name: "Suggestion" })).toBeChecked();
  });

  it("offers no Comment without comment_review", async () => {
    openWorkspace(["finish_review"]);
    await screen.findByRole("tab", { name: /Threads/ });
    expect(screen.queryByRole("button", { name: "Comment" })).toBeNull();
  });

  it("opens a thread from its pin, drawn on the Version it quotes", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(await screen.findByRole("button", { name: "Thread 1, ITSO, Must fix" }));
    expect(screen.getByRole("tab", { name: /Threads/ })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(screen.getByRole("article", { name: "Thread 1, ITSO" })).toHaveFocus());
  });

  it("shows a party's open threads from Readiness, which Details holds (IR-1094)", async () => {
    const user = userEvent.setup();
    openWorkspace();
    await user.click(await screen.findByRole("tab", { name: "Details" }));
    await user.click(await screen.findByRole("button", { name: "Show threads" }));
    expect(screen.getByText(/Showing ITSO's threads/)).toBeInTheDocument();
    const panel = within(screen.getByRole("tabpanel", { name: /Threads/ }));
    expect(panel.getByRole("article", { name: "Thread 1, ITSO" })).toBeInTheDocument();
    expect(panel.queryByRole("article", { name: /Adviser/ })).toBeNull();
  });

  it("finishes the review from the footer, and no longer offers each verdict apart", async () => {
    const user = userEvent.setup();
    openWorkspace();
    const footer = within(screen.getByRole("contentinfo", { name: "Your part" }));
    expect(await footer.findByText(/1 draft comment, not sent/)).toBeInTheDocument();
    expect(footer.queryByRole("button", { name: "Clear…" })).toBeNull();
    expect(footer.queryByRole("button", { name: "Request Revision…" })).toBeNull();
    await user.click(footer.getByRole("button", { name: "Finish review…" }));
    expect(await screen.findByRole("dialog", { name: "Finish your review" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Clear for ITSO/ })).toHaveAccessibleDescription(
      "Unavailable: ITSO has 1 open Must fix thread.",
    );
  });

  // The server offers `open_review` for every open seat, an opened one included
  // (core/permissions.py); found by hand on #595.
  it("offers Finish review to an opened seat even while open_review is offered", async () => {
    openWorkspace(["open_review", "comment_review", "finish_review", "office_review"]);
    const footer = within(await screen.findByRole("contentinfo", { name: "Your part" }));
    expect(footer.getByRole("button", { name: "Finish review…" })).toBeInTheDocument();
    expect(footer.queryByRole("button", { name: "Open review" })).toBeNull();
  });

  it("asks a seat not yet opened to open it, and offers no Finish review", async () => {
    const assigned = { ...record, my_seats: [{ ...record.my_seats[0], state: "assigned" }] } as RecordDetail;
    renderScreen(
      <ReviewWorkspace record={assigned} can={new Set<Capability>(["open_review", "finish_review", "office_review"])}
        reader={<StandInReader />} timelineVersion={0} onChanged={() => {}} documents={null} documentsOpen={false}
        onDocuments={() => {}} />,
    );
    const footer = within(await screen.findByRole("contentinfo", { name: "Your part" }));
    expect(footer.getByRole("button", { name: "Open review" })).toBeInTheDocument();
    expect(footer.queryByRole("button", { name: "Finish review…" })).toBeNull();
  });

  it("keeps the verdict buttons where finish_review is not granted", async () => {
    openWorkspace(["office_review"]);
    expect(await screen.findByRole("button", { name: "Clear…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finish review…" })).toBeNull();
  });

  it("gives the owner Readiness, whose open-thread link opens Threads", async () => {
    const user = userEvent.setup();
    renderScreen(
      <ReviewWorkspace record={record} authorView can={new Set<Capability>(["comment_review"])} reader={<StandInReader />}
        timelineVersion={0} onChanged={() => {}} documents={null} documentsOpen={false} onDocuments={() => {}} />,
    );
    await user.click(await screen.findByRole("button", { name: "Show threads" }));
    expect(screen.getByRole("tab", { name: /Threads/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/Showing ITSO's threads/)).toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations with Threads open", async () => {
    const user = userEvent.setup();
    const { container } = openWorkspace();
    await user.click(await screen.findByRole("tab", { name: /Threads/ }));
    await screen.findByRole("article", { name: "Thread 1, ITSO" });
    await expectNoBlockingA11yViolations(container);
  });

describe("the response to reviewers when a reviewer looks again (IR-876)", () => {
  it("opens Threads on the letter the newest Version was submitted with", async () => {
    api.responseLetters.mockResolvedValue({ data: [LETTER(2)] });
    openWorkspace();
    const letter = await screen.findByRole("region", { name: "Response to reviewers, v2" });
    expect(screen.getByRole("tab", { name: /Threads/ })).toHaveAttribute("aria-selected", "true");
    expect(letter).toHaveTextContent("Addressed: Section 3.2 names it.");
  });

  it("stays on the conversation when the letter is an older Version's", async () => {
    api.responseLetters.mockResolvedValue({ data: [LETTER(1)] });
    openWorkspace();
    await waitFor(() => expect(api.responseLetters).toHaveBeenCalled());
    expect(screen.getByRole("tab", { name: /Conversation/ })).toHaveAttribute("aria-selected", "true");
  });
});
});
