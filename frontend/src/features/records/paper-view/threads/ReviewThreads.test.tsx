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

const reviews = vi.hoisted(() => ({ savedReplies: vi.fn() }));
vi.mock("@/api/reviews", () => ({ reviewsApi: reviews }));

const api = vi.hoisted(() => ({
  postReviewComment: vi.fn(),
  resolveThread: vi.fn(),
  reopenThread: vi.fn(),
  answerThread: vi.fn(),
  changeThreadSeverity: vi.fn(),
  deleteReviewComment: vi.fn(),
  editReviewComment: vi.fn(),
  postThread: vi.fn(),
  reviewMentionable: vi.fn(),
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

// IR-1191: the answer is one row in the history, at the moment it was given.
describe("the authors' answer sits in the thread's history", () => {
  const rows = () =>
    within(screen.getByRole("list", { name: "Replies and history" })).getAllByRole("listitem").map((li) => li.textContent);
  const answered = (over: Partial<NonNullable<ReviewComment["answer"]>> = {}) => ({
    kind: "addressed" as const, note: "Consent script added as Appendix C.", by: "Sam Student",
    at: "2026-10-07T00:00:00Z", ...over,
  });

  it("orders the answer between the replies around it, and draws no separate box", () => {
    setup([
      comment({ id: 1, answer: answered(), events: [
        { kind: "answered", actor_name: "Sam Student", from: null, to: "addressed", at: "2026-10-07T00:00:00Z" },
      ] }),
      comment({ id: 2, reply_to: 1, party: null, party_label: "Author", body: "Is a verbal script enough?", created_at: "2026-10-02T00:00:00Z" }),
      comment({ id: 3, reply_to: 1, party: null, party_label: "IERC", body: "Note the date each firm agreed.", created_at: "2026-10-09T00:00:00Z" }),
    ]);
    expect(rows()).toEqual([
      expect.stringContaining("Is a verbal script enough?"),
      expect.stringContaining("Sam Student marked this Addressed"),
      expect.stringContaining("Note the date each firm agreed."),
    ]);
    // Said once, in the history: no box above the replies, no second "answered" line.
    const t = within(thread(/Thread 1/));
    expect(t.getAllByText("Consent script added as Appendix C.")).toHaveLength(1);
    expect(t.queryByText(/answered it/)).toBeNull();
    // The state badge at the top still says an answer exists, outside the history.
    const history = screen.getByRole("list", { name: "Replies and history" });
    expect(t.getAllByText("Addressed").filter((el) => !history.contains(el))).toHaveLength(1);
  });

  it("puts a reply posted after the answer below it", () => {
    setup([
      comment({ id: 1, answer: answered({ kind: "declined", note: "Out of scope.", by: "Ana Cruz", at: "2026-10-03T00:00:00Z" }) }),
      comment({ id: 2, reply_to: 1, party: null, body: "Understood.", created_at: "2026-10-04T00:00:00Z" }),
    ]);
    expect(rows()).toEqual([
      expect.stringContaining("Ana Cruz declined this"),
      expect.stringContaining("Understood."),
    ]);
    expect(rows()[0]).toContain("Out of scope.");
  });

  it("dates an answer by its event when it carries no time, and keeps an earlier answer as a line", () => {
    setup([comment({ id: 1, answer: answered({ at: null }), events: [
      { kind: "answered", actor_name: "Sam Student", from: null, to: "declined", at: "2026-10-01T00:00:00Z" },
      { kind: "answered", actor_name: "Sam Student", from: null, to: "addressed", at: "2026-10-05T00:00:00Z" },
    ] })]);
    expect(rows()).toEqual([
      expect.stringContaining("Sam Student answered it"),
      expect.stringContaining("Sam Student marked this Addressed Oct 5, 2026"),
    ]);
  });

  it("says when no note was given, and names the authors when the server names no one", () => {
    setup([comment({ id: 1, answer: answered({ note: "", by: null }) })]);
    expect(rows()).toEqual([expect.stringContaining("The authors marked this Addressed")]);
    expect(rows()[0]).toContain("No answer given.");
  });
});

// IR-1192: a reply says who wrote it, as the Conversation tab does.
describe("a thread's replies", () => {
  it("show the writer, their party and the date, and the Reply control counts them", () => {
    setup([
      comment({ id: 1 }),
      comment({ id: 2, reply_to: 1, party: null, author_name: "Dr. Marco Lim", party_label: "IERC", body: "Attach it.", created_at: "2026-10-03T00:00:00Z", edited_at: "2026-10-04T00:00:00Z" }),
      // An older payload: no label from the server.
      comment({ id: 3, reply_to: 1, party: null, author_name: "Sam Student", party_label: undefined, body: "Will do.", created_at: "2026-10-05T00:00:00Z" }),
    ]);
    const [first, second] = within(screen.getByRole("list", { name: "Replies and history" })).getAllByRole("listitem");
    expect(within(first).getByText("Dr. Marco Lim")).toBeInTheDocument();
    expect(within(first).getByText("IERC")).toBeInTheDocument();
    expect(first).toHaveTextContent("Oct 3, 2026");
    expect(first).toHaveTextContent("edited");
    expect(within(second).getByText("Sam Student")).toBeInTheDocument();
    expect(second).toHaveTextContent("Will do.");
    expect(within(thread(/Thread 1/)).getByRole("button", { name: "Reply, 2 replies" })).toBeInTheDocument();
  });

  it("edits the viewer's own reply from its menu", async () => {
    api.editReviewComment.mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    const { reload } = setup([
      comment({ id: 1 }),
      comment({ id: 2, reply_to: 1, party: null, author_name: "Sam Student", body: "mmm", can_edit: true }),
      comment({ id: 3, reply_to: 1, party: null, author_name: "Dr. Marco Lim", body: "Attach it." }),
    ]);
    // Only the reply the server says is theirs has a menu.
    expect(screen.queryByRole("button", { name: "Actions for Dr. Marco Lim's reply" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Actions for Sam Student's reply" }));
    await user.click(screen.getByRole("menuitem", { name: "Edit" }));
    const box = screen.getByRole("textbox", { name: "Edit your reply" });
    expect(box).toHaveValue("mmm");
    expect(box).toHaveFocus();
    await user.clear(box);
    await user.keyboard("Will attach the script.");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(api.editReviewComment).toHaveBeenCalledWith(9, 2, { body: "Will attach the script." });
    expect(reload).toHaveBeenCalled();
  });

  it("offers no Edit without comment_review", () => {
    setup([comment({ id: 1 }), comment({ id: 2, reply_to: 1, party: null, author_name: "Sam Student", can_edit: true })], { caps: [] });
    expect(screen.queryByRole("button", { name: "Actions for Sam Student's reply" })).toBeNull();
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
    expect(drafts.getByText("Only you see these until you post them or finish your review")).toBeInTheDocument();
    const draft = within(drafts.getByRole("article", { name: /Draft D1/ }));
    // The place is a link to the passage (IR-1139).
    expect(draft.getByRole("button", { name: "Go to page 3 of v2" })).toHaveTextContent("p. 3 · v2");
    expect(draft.queryByRole("button", { name: "Post" })).toBeNull();
    await user.click(draft.getByRole("button", { name: "Discard" }));
    expect(api.deleteReviewComment).toHaveBeenCalledWith(9, 2);
  });

  it("posts one draft on its own where the server allows it (IR-1194)", async () => {
    const user = userEvent.setup();
    const { reload, onChanged } = setup([comment({ id: 2, is_draft: true, can_post: true, can_delete: true })]);
    const draft = within(screen.getByRole("article", { name: /Draft D1/ }));
    await user.click(draft.getByRole("button", { name: "Post" }));
    expect(api.postThread).toHaveBeenCalledWith(9, 2);
    expect(reload).toHaveBeenCalled();
    expect(onChanged).toHaveBeenCalled();
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
    expect(screen.getByText(/Post sends it now and tells the authors/)).toBeInTheDocument();
    const box = screen.getByRole("textbox", { name: "Comment" });
    expect(box).toHaveFocus();
    await user.keyboard("94% of what?");
    // Saved replies (IR-877) sit right under the box.
    await user.tab();
    expect(screen.getByRole("button", { name: "Saved replies" })).toHaveFocus();
    // Then whom to mention (IR-877).
    await user.tab();
    expect(screen.getByRole("button", { name: "Mention someone" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("radio", { name: "Suggestion" })).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("radio", { name: "Must fix" })).toBeChecked();
    // Suggested wording (IR-876) is optional and comes after the severity.
    await user.tab();
    expect(screen.getByRole("textbox", { name: "Suggested wording (optional)" })).toHaveFocus();
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Save as draft" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(api.postReviewComment).toHaveBeenCalledWith(9, {
      body: "94% of what?",
      kind: "thread",
      severity: "must_fix",
      post_now: false,
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
    expect(api.postReviewComment).toHaveBeenCalledWith(9, { body: "A question for the panel.", kind: "thread" });
  });

  it("posts a reviewer's thread now with Post, which Enter in the box also does (IR-1194)", async () => {
    const user = userEvent.setup();
    const { onCompose } = setup([], { composing: { kind: "general" }, caps: ["comment_review", "finish_review", "open_general_thread"] });
    await user.keyboard("Cite the prior patent.");
    expect(screen.getByRole("button", { name: "Save as draft" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Post" }));
    expect(api.postReviewComment).toHaveBeenCalledWith(9, {
      body: "Cite the prior patent.", kind: "thread", severity: "suggestion", post_now: true,
    });
    expect(onCompose).toHaveBeenCalledWith(null);
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

  it("inserts a saved reply into the comment (IR-877)", async () => {
    reviews.savedReplies.mockResolvedValue({ data: { results: [
      { id: 1, title: "Cite", body: "Please cite the source.", created_at: "", updated_at: "" },
    ], limit: 50 } });
    const user = userEvent.setup();
    setup([], { composing: { kind: "general" } });
    await user.click(screen.getByRole("button", { name: "Saved replies" }));
    await user.click(await screen.findByRole("button", { name: "Insert “Cite”" }));
    expect(screen.getByRole("textbox", { name: "Comment" })).toHaveValue("Please cite the source.");
  });

  it("opens a general thread from New comment", async () => {
    const user = userEvent.setup();
    const { onCompose } = setup([], { caps: ["comment_review", "open_general_thread"] });
    await user.click(screen.getByRole("button", { name: "New comment" }));
    expect(onCompose).toHaveBeenCalledWith({ kind: "general" });
  });

  it("offers no New comment where the server allows only threads on a passage (IR-1194)", () => {
    setup([]);
    expect(screen.queryByRole("button", { name: "New comment" })).toBeNull();
    expect(screen.getByText(/A remark on the whole paper goes in Conversation\./)).toBeInTheDocument();
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
