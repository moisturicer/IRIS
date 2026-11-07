/**
 * The Threads tab (ADR-032 §7, IR-875): the composer, drafts, filters and
 * each thread's controls. Every control follows the comment's own `can_*`
 * flag or a granted capability -- the fixtures never name a role -- and
 * every query goes through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Capability } from "@/features/records/capabilities";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { ReviewComment } from "@/types/records";

import { ReviewThreads, type CommentTarget, type ReviewThreadsProps } from "./ReviewThreads";
import { comment } from "./threadFixtures";
import { groupThreads } from "./threadModel";

const api = vi.hoisted(() => ({
  postReviewComment: vi.fn(),
  resolveThread: vi.fn(),
  reopenThread: vi.fn(),
  answerThread: vi.fn(),
  changeThreadSeverity: vi.fn(),
  deleteReviewComment: vi.fn(),
}));
vi.mock("@/api/records", () => ({ recordsApi: api }));

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset().mockResolvedValue({ data: {} }));
});

function setup(comments: ReviewComment[], over: Partial<ReviewThreadsProps> & { caps?: Capability[] } = {}) {
  const reload = vi.fn();
  const onChanged = vi.fn();
  const onCompose = vi.fn();
  const onShowInPaper = vi.fn();
  const props: ReviewThreadsProps = {
    recordId: 9,
    can: new Set<Capability>(over.caps ?? ["comment_review"]),
    threads: { loaded: true, failed: false, reload, ...groupThreads(comments) },
    viewer: { userId: 5, party: "itso" },
    composing: null,
    onCompose,
    onChanged,
    onShowInPaper,
    party: null,
    onClearParty: vi.fn(),
    focus: null,
    ...over,
  };
  const view = renderScreen(<ReviewThreads {...props} />);
  return { ...view, reload, onChanged, onCompose, onShowInPaper, props };
}

const thread = (name: RegExp | string) => screen.getByRole("article", { name });

describe("a thread's controls follow its flags", () => {
  it("offers Resolve, Reply and a severity change only where the server allows them", () => {
    setup([
      comment({ id: 1, party: "itso", party_label: "ITSO", severity: "must_fix", can_resolve: true, can_change_severity: true }),
      comment({ id: 2, party: "adviser", party_label: "Adviser" }),
    ]);
    const first = within(thread("Thread 1, ITSO"));
    expect(first.getByRole("button", { name: "Resolve" })).toBeInTheDocument();
    expect(first.getByRole("button", { name: "Change to Suggestion" })).toBeInTheDocument();
    expect(first.getByText("Must fix")).toBeInTheDocument();
    expect(first.getByText("No answer")).toBeInTheDocument();

    const second = within(thread("Thread 2, Adviser"));
    expect(second.queryByRole("button", { name: "Resolve" })).toBeNull();
    expect(second.queryByRole("button", { name: /Change to/ })).toBeNull();
    expect(second.queryByRole("button", { name: "Mark addressed" })).toBeNull();
    expect(second.getByRole("button", { name: "Reply" })).toBeInTheDocument();
  });

  it("offers no Reply without comment_review", () => {
    setup([comment({ id: 1 })], { caps: [] });
    expect(within(thread(/Thread 1/)).queryByRole("button", { name: "Reply" })).toBeNull();
  });

  it("resolves through the thread's own act, then reads everything again", async () => {
    const user = userEvent.setup();
    const { reload, onChanged } = setup([comment({ id: 1, can_resolve: true })]);
    await user.click(within(thread(/Thread 1/)).getByRole("button", { name: "Resolve" }));
    expect(api.resolveThread).toHaveBeenCalledWith(9, 1);
    expect(reload).toHaveBeenCalled();
    expect(onChanged).toHaveBeenCalled();
  });

  it("shows the server's refusal beside the thread", async () => {
    api.reopenThread.mockRejectedValue({ response: { status: 403, data: { detail: "Not yours to reopen." } } });
    const user = userEvent.setup();
    setup([comment({ id: 1, state: "resolved", can_reopen: true })]);
    await user.click(screen.getByRole("button", { name: "Resolved 1" }));
    await user.click(within(thread(/Thread 1/)).getByRole("button", { name: "Reopen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Not yours to reopen.");
  });
});

describe("an owner answers a reviewer's thread", () => {
  it("marks it addressed, saying where, by keyboard", async () => {
    const user = userEvent.setup();
    setup([comment({ id: 4, party_label: "Adviser", can_answer: true })]);
    await user.click(within(thread(/Thread 1/)).getByRole("button", { name: "Mark addressed" }));
    const where = screen.getByRole("textbox", { name: "Where you addressed it" });
    expect(where).toHaveFocus();
    expect(screen.getByRole("button", { name: "Mark addressed" })).toBeDisabled();
    await user.keyboard("§4, p. 9");
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Mark addressed" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(api.answerThread).toHaveBeenCalledWith(9, 4, { answer: "addressed", note: "§4, p. 9" });
  });

  it("shows the answer and its state once given", () => {
    setup([comment({ id: 4, answer: { kind: "declined", note: "Out of scope.", by: "Ana Cruz", at: null } })]);
    const t = within(thread(/Thread 1/));
    expect(t.getByText("Declined")).toBeInTheDocument();
    expect(t.getByText("Out of scope.")).toBeInTheDocument();
  });
});

describe("a thread's history", () => {
  it("lists replies and events together, oldest first (found by hand on #595)", async () => {
    const user = userEvent.setup();
    setup([
      comment({ id: 1, state: "closed", events: [
        { kind: "closed_by_decision", actor_name: "RDCO", from: null, to: null, at: "2026-11-05T00:00:00Z" },
        { kind: "severity_changed", actor_name: "Ana Cruz", from: "must_fix", to: "suggestion", at: "2026-11-02T00:00:00Z" },
      ] }),
      comment({ id: 2, reply_to: 1, party: null, severity: null, state: null, body: "Done in §4.", created_at: "2026-11-03T00:00:00Z" }),
    ]);
    await user.click(screen.getByRole("button", { name: "Resolved 1" }));
    const items = within(screen.getByRole("list", { name: "Replies and history" })).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringContaining("Ana Cruz changed it to Suggestion"),
      expect.stringContaining("Done in §4."),
      expect.stringContaining("Closed by the Decision"),
    ]);
  });
});

describe("drafts", () => {
  it("lists the viewer's drafts apart, each with Discard where the server allows it", async () => {
    const user = userEvent.setup();
    setup([
      comment({ id: 1 }),
      comment({ id: 2, is_draft: true, can_delete: true, anchor: { version: 2, page: 3, quote: "an accuracy of 94%" } }),
    ]);
    const drafts = within(screen.getByRole("region", { name: "Your drafts" }));
    expect(drafts.getByText("Only you see these until you finish")).toBeInTheDocument();
    const draft = within(drafts.getByRole("article", { name: /Draft D1/ }));
    expect(draft.getByText("p.3 · v2")).toBeInTheDocument();
    await user.click(draft.getByRole("button", { name: "Discard" }));
    expect(api.deleteReviewComment).toHaveBeenCalledWith(9, 2);
  });
});

describe("filters", () => {
  it("files resolved and closed threads under Resolved, and counts each filter", async () => {
    const user = userEvent.setup();
    setup([
      comment({ id: 1, author: 5 }),
      comment({ id: 2, state: "resolved" }),
      comment({ id: 3, state: "closed", closed_reason: "Published as is." }),
    ]);
    expect(screen.getByRole("button", { name: "Open 1" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Yours 1" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Resolved 2" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
    expect(screen.getByText("Closed by the Decision: Published as is.")).toBeInTheDocument();
  });

  it("narrows to the party Readiness pointed at", () => {
    setup([comment({ id: 1, party: "itso", party_label: "ITSO" }), comment({ id: 2, party: "adviser" })], { party: "itso" });
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText(/Showing ITSO's threads/)).toBeInTheDocument();
  });
});

describe("the composer", () => {
  const passage: CommentTarget = {
    kind: "passage", version: 3,
    passage: { page: 9, quote: "an accuracy of 94%", prefix: "reports ", suffix: " against", regions: [{ page: 9, left: 0.1, top: 0.2, right: 0.5, bottom: 0.22 }] },
  };

  it("adds an anchored Must fix draft by keyboard alone", async () => {
    const user = userEvent.setup();
    const { onCompose, reload } = setup([], { composing: passage, caps: ["comment_review", "finish_review"] });
    expect(screen.getByText("“an accuracy of 94%”")).toBeInTheDocument();
    expect(screen.getByText("Held as a draft until you finish your review.")).toBeInTheDocument();
    const box = screen.getByRole("textbox", { name: "Comment" });
    expect(box).toHaveFocus();
    await user.keyboard("94% of what?");
    await user.tab();
    expect(screen.getByRole("radio", { name: "Suggestion" })).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("radio", { name: "Must fix" })).toBeChecked();
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Add to review" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(api.postReviewComment).toHaveBeenCalledWith(9, {
      body: "94% of what?",
      severity: "must_fix",
      anchor: { version: 3, page: 9, quote: "an accuracy of 94%", prefix: "reports ", suffix: " against",
        regions: [{ page: 9, left: 0.1, top: 0.2, right: 0.5, bottom: 0.22 }] },
    });
    expect(onCompose).toHaveBeenCalledWith(null);
    expect(reload).toHaveBeenCalled();
  });

  it("asks no severity where the server holds nothing as a draft", async () => {
    const user = userEvent.setup();
    setup([], { composing: { kind: "general" }, caps: ["comment_review"] });
    expect(screen.queryByRole("radio")).toBeNull();
    await user.keyboard("A question for the panel.");
    await user.click(screen.getByRole("button", { name: "Comment" }));
    expect(api.postReviewComment).toHaveBeenCalledWith(9, { body: "A question for the panel." });
  });

  it("keeps the text when the server refuses it", async () => {
    api.postReviewComment.mockRejectedValue({ response: { status: 400, data: { detail: "Quote the passage you're commenting on." } } });
    const user = userEvent.setup();
    setup([], { composing: passage });
    await user.keyboard("Hmm.");
    await user.click(screen.getByRole("button", { name: "Comment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Quote the passage you're commenting on. Your text is kept.");
    expect(screen.getByRole("textbox", { name: "Comment" })).toHaveValue("Hmm.");
  });

  it("opens a general thread from New comment", async () => {
    const user = userEvent.setup();
    const { onCompose } = setup([]);
    await user.click(screen.getByRole("button", { name: "New comment" }));
    expect(onCompose).toHaveBeenCalledWith({ kind: "general" });
  });
});

it("shows a passage in the paper from its quote", async () => {
  const user = userEvent.setup();
  const { onShowInPaper } = setup([comment({ id: 1, anchor: { version: 1, page: 2, quote: "low-cost sensors" } })]);
  await user.click(screen.getByRole("button", { name: "Show in paper: “low-cost sensors”" }));
  expect(onShowInPaper).toHaveBeenCalledWith(expect.objectContaining({ pin: "1" }));
});

it("has no serious or critical accessibility violations", async () => {
  const { container } = setup(
    [
      comment({ id: 1, severity: "must_fix", can_resolve: true, anchor: { version: 1, page: 2, quote: "x y" } }),
      comment({ id: 2, is_draft: true, can_delete: true }),
      comment({ id: 3, reply_to: 1, party: null, severity: null, state: null }),
    ],
    { composing: { kind: "general" }, caps: ["comment_review", "finish_review"] },
  );
  await expectNoBlockingA11yViolations(container);
});
