/**
 * The Review section's timeline as a reader meets it (IR-412). What goes into
 * it, and in which order, is `timelineEntries.test.ts`'s; this file checks it
 * renders that from the tracker, and that it never presents a retired party
 * such as Intake as where the record is now (spec §0, invariant 1).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import type { RecordTracker, ReviewComment } from "@/types/records";

import { recordsApi } from "@/api/records";

import { ReviewTimeline } from "./ReviewTimeline";

vi.mock("@/api/records", () => ({
  recordsApi: { tracker: vi.fn(), postReviewComment: vi.fn(), editReviewComment: vi.fn() },
}));

const tracker = vi.mocked(recordsApi.tracker);
const postComment = vi.mocked(recordsApi.postReviewComment);
const editComment = vi.mocked(recordsApi.editReviewComment);

const comment = (overrides: Partial<ReviewComment>): ReviewComment => ({
  id: 1,
  author: 3,
  author_name: "Rhea Owner",
  body: "Is the consent form attached?",
  version: 1,
  reply_to: null,
  created_at: "2026-09-06T08:00:00Z",
  edited_at: null,
  can_edit: false,
  ...overrides,
});

const payload: RecordTracker = {
  record_id: 7,
  record_type: "Thesis / Research",
  workflow_state: "in_review",
  workflow_state_label: "In review",
  // The legacy pipeline can still hold a record at Intake until IR-260.
  current_holders: [{ party: "intake", label: "Intake (retired)", opened_at: null, opened_by: null }],
  parties: [
    {
      party: "intake", label: "Intake (retired)", state: "active", state_label: "Reviewing",
      started: false, outcome: null, outcome_label: null, at: null, preserved: false,
      awaiting_document: null, outcome_earlier: false, in_pool: false, changes_requested: false,
      seats: null,
      carryover: null, carryover_version: null, carryover_label: null,
      due_at: null, original_due_at: null, is_overdue: false, clock_paused: false,
      can_extend: false, extensions: [],
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
  review_comments: [],
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

  describe("the review discussion (IR-419)", () => {
    const discussion = (comments: ReviewComment[]) => ({ ...payload, review_comments: comments });

    it("shows each comment, by its author, with its version and its replies under it", async () => {
      respond(discussion([
        comment({ id: 1, body: "Which sample size?", author_name: "Mara Santos" }),
        comment({
          id: 2, reply_to: 1, body: "Forty respondents.", created_at: "2026-09-07T08:00:00Z",
          edited_at: "2026-09-07T09:00:00Z",
        }),
      ]));
      const { container } = renderScreen(<ReviewTimeline recordId={7} />);

      const list = await screen.findByRole("list", { name: "Review timeline" });
      const thread = within(list).getByText("Which sample size?").closest("li")!;
      expect(thread).toHaveTextContent("Mara Santos");
      expect(thread).toHaveTextContent("Made against v1");
      const replies = within(thread).getByRole("list", { name: "Replies to Mara Santos" });
      const [reply] = within(replies).getAllByRole("listitem");
      expect(reply).toHaveTextContent("Forty respondents.");
      expect(reply).toHaveTextContent("Rhea Owner");
      expect(reply).toHaveTextContent("Edited");
      await expectNoBlockingA11yViolations(container);
    });

    it("offers no composer, reply or edit to a viewer who may not comment", async () => {
      respond(discussion([comment({ can_edit: true })]));
      renderScreen(<ReviewTimeline recordId={7} />);

      await screen.findByRole("list", { name: "Review timeline" });
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /reply|edit|^comment$/i })).not.toBeInTheDocument();
    });

    it("posts a comment and reads the timeline again", async () => {
      respond(discussion([]));
      postComment.mockResolvedValue({ data: comment({ id: 9 }) } as never);
      const { container } = renderScreen(<ReviewTimeline recordId={7} canComment />);

      await userEvent.type(await screen.findByRole("textbox", { name: "Comment" }), "  Is it attached?  ");
      respond(discussion([comment({ id: 9, body: "Is it attached?" })]));
      await userEvent.click(screen.getByRole("button", { name: "Comment" }));

      expect(postComment).toHaveBeenCalledWith(7, { body: "Is it attached?" });
      expect(await screen.findByText("Is it attached?")).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: "Comment" })).toHaveValue("");
      expect(tracker).toHaveBeenCalledTimes(2);
      await expectNoBlockingA11yViolations(container);
    });

    it("will not post an empty comment", async () => {
      respond(discussion([]));
      renderScreen(<ReviewTimeline recordId={7} canComment />);

      await screen.findByRole("textbox", { name: "Comment" });
      expect(screen.getByRole("button", { name: "Comment" })).toBeDisabled();
    });

    it("keeps what was written beside the server's refusal", async () => {
      respond(discussion([]));
      postComment.mockRejectedValue({ response: { data: { detail: "A draft is not under review." } } });
      renderScreen(<ReviewTimeline recordId={7} canComment />);

      const box = await screen.findByRole("textbox", { name: "Comment" });
      await userEvent.type(box, "Hello");
      await userEvent.click(screen.getByRole("button", { name: "Comment" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("A draft is not under review.");
      expect(box).toHaveValue("Hello");
    });

    it("replies in the thread of the comment answered", async () => {
      respond(discussion([comment({ id: 4, author_name: "Mara Santos", body: "Which sample size?" })]));
      postComment.mockResolvedValue({ data: comment({ id: 5, reply_to: 4 }) } as never);
      renderScreen(<ReviewTimeline recordId={7} canComment />);

      await userEvent.click(await screen.findByRole("button", { name: "Reply to Mara Santos" }));
      await userEvent.type(screen.getByRole("textbox", { name: "Reply to Mara Santos" }), "Forty.");
      await userEvent.click(screen.getByRole("button", { name: "Send reply" }));

      expect(postComment).toHaveBeenCalledWith(7, { body: "Forty.", reply_to: 4 });
    });

    it("offers Edit only on a comment the server says this viewer may edit", async () => {
      respond(discussion([
        comment({ id: 1, body: "Mine.", can_edit: true }),
        comment({ id: 2, body: "Theirs.", can_edit: false, created_at: "2026-09-07T08:00:00Z" }),
      ]));
      editComment.mockResolvedValue({ data: comment({ id: 1, body: "Mine, fixed." }) } as never);
      renderScreen(<ReviewTimeline recordId={7} canComment />);

      const list = await screen.findByRole("list", { name: "Review timeline" });
      const theirs = within(list).getByText("Theirs.").closest("li")!;
      expect(within(theirs).queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: "Edit your comment" }));
      const box = screen.getByRole("textbox", { name: "Edit your comment" });
      expect(box).toHaveValue("Mine.");
      await userEvent.clear(box);
      await userEvent.type(box, "Mine, fixed.");
      await userEvent.click(screen.getByRole("button", { name: "Save" }));

      expect(editComment).toHaveBeenCalledWith(7, 1, { body: "Mine, fixed." });
    });
  });
});
