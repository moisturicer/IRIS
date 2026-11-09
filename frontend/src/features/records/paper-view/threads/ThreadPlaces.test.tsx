/**
 * Where a thread's passage is now, and suggested wording (ADR-032 §7,
 * IR-876). What a card says comes from the thread's own `place`,
 * `outdated_since` and `suggestion`; every query goes through the
 * accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Capability } from "@/features/records/capabilities";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { ReviewComment, ThreadPlace } from "@/types/records";

import { ReviewThreads, type ReviewThreadsProps } from "./ReviewThreads";
import { comment } from "./threadFixtures";
import { groupThreads } from "./threadModel";

const api = vi.hoisted(() => ({
  postReviewComment: vi.fn(),
  answerThread: vi.fn(),
}));
vi.mock("@/api/records", () => ({ recordsApi: api }));

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset().mockResolvedValue({ data: {} }));
});

const ANCHOR = { version: 1, page: 3, quote: "forty respondents", prefix: "", suffix: "", regions: [] };

function place(over: Partial<ThreadPlace>): ThreadPlace {
  return { version: 2, outcome: "found", page: 3, text: "forty respondents", regions: [], suggestion_page: null, ...over };
}

function setup(comments: ReviewComment[], over: Partial<ReviewThreadsProps> & { caps?: Capability[] } = {}) {
  const props: ReviewThreadsProps = {
    recordId: 9,
    can: new Set<Capability>(over.caps ?? ["comment_review"]),
    threads: { loaded: true, failed: false, reload: vi.fn(), ...groupThreads(comments) },
    viewer: { userId: 5, party: null },
    composing: null,
    onCompose: vi.fn(),
    onChanged: vi.fn(),
    onShowInPaper: vi.fn(),
    party: null,
    onClearParty: vi.fn(),
    focus: null,
    ...over,
  };
  return { ...renderScreen(<ReviewThreads {...props} />), props };
}

const card = () => screen.getByRole("article");

describe("where a thread's passage is now", () => {
  it("an edited passage reads Outdated, with the new passage beside the original", async () => {
    const { container } = setup([comment({
      anchor: ANCHOR, outdated_since: 2,
      place: place({ outcome: "changed", page: 4, text: "forty-two respondents in all" }),
    })]);

    expect(within(card()).getByText("Outdated since v2")).toBeInTheDocument();
    const now = within(card()).getByRole("region", { name: "Now in v2, p. 4" });
    expect(now).toHaveTextContent("forty-two respondents in all");
    // The original passage is still the thread's own.
    expect(within(card()).getByRole("button", { name: "Show in paper: “forty respondents”" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("a removed passage says so", () => {
    setup([comment({ anchor: ANCHOR, outdated_since: 3, place: place({ version: 3, outcome: "removed", page: null, text: "" }) })]);
    expect(within(card()).getByText("Outdated since v3")).toBeInTheDocument();
    expect(within(card()).getByText("Passage removed in v3.")).toBeInTheDocument();
  });

  it("a passage found in a later Version says where it is now and is not Outdated", () => {
    setup([comment({ anchor: ANCHOR, outdated_since: null, place: place({ page: 5 }) })]);
    expect(within(card()).getByText("Found on p. 5 of v2.")).toBeInTheDocument();
    expect(within(card()).queryByText(/Outdated/)).not.toBeInTheDocument();
  });

  it("a thread followed after going Outdated stays Outdated and shows its newest place", () => {
    setup([comment({
      anchor: ANCHOR, outdated_since: 2,
      place: place({ version: 3, outcome: "found", page: 6, text: "forty-two respondents in all" }),
    })]);
    expect(within(card()).getByText("Outdated since v2")).toBeInTheDocument();
    expect(within(card()).getByRole("region", { name: "Now in v3, p. 6" })).toHaveTextContent("forty-two respondents in all");
  });
});

describe("suggested wording", () => {
  const suggested = (over: Partial<ReviewComment> = {}) =>
    comment({ anchor: ANCHOR, suggestion: "forty-two respondents", ...over });

  it("is shown on the thread", () => {
    setup([suggested()]);
    expect(within(card()).getByRole("region", { name: "Suggested wording" })).toHaveTextContent("forty-two respondents");
  });

  it("the owner accepts it, which marks the thread addressed", async () => {
    setup([suggested({ can_answer: true })]);
    await userEvent.click(within(card()).getByRole("button", { name: "Accept wording" }));
    expect(api.answerThread).toHaveBeenCalledWith(9, expect.any(Number), { answer: "addressed", note: "" });
  });

  it("declining it asks for a reason", async () => {
    setup([suggested({ can_answer: true })]);
    await userEvent.click(within(card()).getByRole("button", { name: "Decline" }));
    expect(within(card()).getByRole("button", { name: "Decline" })).toBeDisabled();
    await userEvent.type(within(card()).getByLabelText("Why you're declining it"), "The count is right.");
    await userEvent.click(within(card()).getByRole("button", { name: "Decline" }));
    expect(api.answerThread).toHaveBeenCalledWith(9, expect.any(Number), { answer: "declined", note: "The count is right." });
  });

  it("once accepted, the next Version says whether the wording is there", () => {
    const accepted = { kind: "addressed" as const, note: "Accepted the suggested wording.", by: "Juan", at: null };
    const { unmount } = setup([suggested({ answer: accepted, place: place({ suggestion_page: 4 }) })]);
    expect(within(card()).getByText("Suggested wording found on p. 4 of v2.")).toBeInTheDocument();
    unmount();

    setup([suggested({ answer: accepted, place: place({ suggestion_page: null }) })]);
    expect(within(card()).getByText("Suggested wording not found in v2.")).toBeInTheDocument();
  });

  it("a reviewer can suggest wording when commenting on a passage", async () => {
    const passage = { page: 3, quote: "forty respondents", prefix: "", suffix: "", regions: [] };
    setup([], { caps: ["comment_review", "finish_review"], composing: { kind: "passage", version: 1, passage } });

    const form = screen.getByRole("form", { name: "New comment" });
    await userEvent.type(within(form).getByRole("textbox", { name: "Comment" }), "Count again.");
    await userEvent.type(within(form).getByRole("textbox", { name: "Suggested wording (optional)" }), "forty-two respondents");
    await userEvent.click(within(form).getByRole("button", { name: "Add to review" }));

    expect(api.postReviewComment).toHaveBeenCalledWith(9, expect.objectContaining({ suggestion: "forty-two respondents" }));
  });

  it("a general comment offers no wording", () => {
    setup([], { caps: ["comment_review", "finish_review"], composing: { kind: "general" } });
    expect(screen.queryByRole("textbox", { name: /Suggested wording/ })).not.toBeInTheDocument();
  });
});

describe("the response to reviewers in Threads", () => {
  const letter = {
    version: 2, created_at: "2026-11-09T00:00:00Z",
    entries: [
      { thread: 1, party: "ierc", party_label: "IERC", severity: "must_fix" as const, comment: "Add the consent form.",
        version: 1, page: 4, quote: "consent", answer: "addressed" as const, note: "Appendix C." },
      { thread: 2, party: "itso", party_label: "ITSO", severity: "suggestion" as const, comment: "Consider a diagram.",
        version: 1, page: null, quote: "", answer: null, note: "" },
    ],
  };

  it("comes first, whole, with each answer as the authors gave it", async () => {
    const { container } = setup([comment({ anchor: ANCHOR })], { letter });

    const panel = screen.getByRole("region", { name: "Response to reviewers, v2" });
    const items = within(panel).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("IERC");
    expect(items[0]).toHaveTextContent("Addressed: Appendix C.");
    expect(items[1]).toHaveTextContent("No answer given");
    // Before the threads.
    expect(panel.compareDocumentPosition(card()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await expectNoBlockingA11yViolations(container);
  });

  it("isn't shown when no Version carries one", () => {
    setup([comment({ anchor: ANCHOR })], { letter: null });
    expect(screen.queryByRole("region", { name: /Response to reviewers/ })).not.toBeInTheDocument();
  });
});
