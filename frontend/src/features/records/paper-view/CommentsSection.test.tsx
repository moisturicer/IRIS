import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "@/api/records";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { fireEvent, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { PublicComment, PublicCommentsResponse } from "@/types/records";

import { CommentsSection } from "./CommentsSection";

const RECORD_ID = 7;
const VIEWER_ID = 11;

function comment(overrides: Partial<PublicComment> = {}): PublicComment {
  return {
    id: 1,
    author_name: "Ana Reyes",
    body: "A useful paper.",
    created_at: "2026-11-01T09:00:00Z",
    edited_at: null,
    is_author: false,
    can_edit: false,
    can_report: true,
    reply_to: null,
    deletion_kind: null,
    ...overrides,
  };
}

/** A comment at a given day of November, so order is easy to read in a test. */
function onDay(id: number, day: number, overrides: Partial<PublicComment> = {}): PublicComment {
  return comment({ id, author_name: `Reader ${id}`, body: `Body ${id}`, created_at: `2026-11-${String(day).padStart(2, "0")}T09:00:00Z`, ...overrides });
}

const gone = (id: number, day: number, kind: "writer" | "moderator" = "writer", overrides: Partial<PublicComment> = {}) =>
  onDay(id, day, { author_name: null, body: null, deletion_kind: kind, can_report: false, ...overrides });

let current: PublicCommentsResponse;
let loadComments: ReturnType<typeof vi.spyOn>;
let postComment: ReturnType<typeof vi.spyOn>;
let editComment: ReturnType<typeof vi.spyOn>;
let deleteComment: ReturnType<typeof vi.spyOn>;
let reportComment: ReturnType<typeof vi.spyOn>;

function renderComments(viewerId: number | null = VIEWER_ID) {
  return renderScreen(<CommentsSection recordId={RECORD_ID} viewerId={viewerId} viewerName="Lee Reader" />);
}

function setComments(comments: PublicComment[]) {
  current = { comments, count: comments.filter((item) => item.deletion_kind === null).length };
}

/** The ids of the top-level comments on the page, in order. */
function topLevelBodies() {
  const list = screen.getByRole("list", { name: "Comments" });
  return within(list)
    .getAllByRole("article")
    .filter((article) => !article.closest('[aria-label^="Replies to"]'))
    .map((article) => article.textContent ?? "");
}

beforeEach(() => {
  current = { comments: [], count: 0 };
  loadComments = vi.spyOn(recordsApi, "publicComments").mockImplementation(async () => ({ data: current } as never));
  postComment = vi.spyOn(recordsApi, "postPublicComment").mockResolvedValue({ data: comment({ id: 99 }) } as never);
  editComment = vi.spyOn(recordsApi, "editPublicComment").mockResolvedValue({ data: comment() } as never);
  deleteComment = vi.spyOn(recordsApi, "deletePublicComment").mockResolvedValue({ data: undefined } as never);
  reportComment = vi.spyOn(recordsApi, "reportPublicComment").mockResolvedValue({ data: undefined } as never);
});

afterEach(() => vi.restoreAllMocks());

describe("published paper comments", () => {
  it("shows an empty state and the live count", async () => {
    renderComments();

    expect(await screen.findByRole("heading", { name: "Comments (0)" })).toBeInTheDocument();
    expect(screen.getByText("No comments yet. Start the discussion.")).toBeInTheDocument();
  });

  it("does not mistake a failed load for an empty thread", async () => {
    loadComments.mockRejectedValueOnce({ response: { status: 429, data: { detail: "Please wait before loading comments." } } });
    renderComments();

    expect(await screen.findByRole("alert")).toHaveTextContent("Please wait before loading comments.");
    expect(screen.queryByText("No comments yet. Start the discussion.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows replies under the comment they answer, with author and edited markers", async () => {
    setComments([
      onDay(2, 2, { author_name: "Lee Reader", body: "A reply", edited_at: "2026-11-02T10:00:00Z", is_author: true, reply_to: 1, can_edit: true, can_report: false }),
      onDay(1, 1, { author_name: "Ana Reyes", body: "First comment" }),
      onDay(3, 3, { body: "Another thread" }),
    ]);
    renderComments();

    expect(await screen.findByRole("heading", { name: "Comments (3)" })).toBeInTheDocument();
    const replies = screen.getByRole("list", { name: "Replies to Ana Reyes" });
    const reply = within(replies).getByRole("article");
    expect(within(reply).getByText("A reply")).toBeInTheDocument();
    expect(within(reply).getByText("Author")).toBeInTheDocument();
    expect(within(reply).getByText("Edited")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Replies to Reader 3" })).not.toBeInTheDocument();
    expect(topLevelBodies()).toHaveLength(2);
  });

  it("gives every comment a time with the full date on it", async () => {
    setComments([onDay(1, 1)]);
    renderComments();

    const time = (await screen.findByRole("article")).querySelector("time");
    expect(time).toHaveAttribute("datetime", "2026-11-01T09:00:00Z");
    expect(time?.getAttribute("title")).toMatch(/2026/);
  });

  it("keeps a reply to a reply in the thread and names who it answers", async () => {
    const user = userEvent.setup();
    setComments([
      onDay(1, 1, { author_name: "Ana Reyes" }),
      onDay(2, 2, { author_name: "Mark Cruz", reply_to: 1 }),
      onDay(3, 3, { author_name: "Lee Jasmin", body: "Thanks Mark", reply_to: 2 }),
    ]);
    renderComments();

    const replies = await screen.findByRole("list", { name: "Replies to Ana Reyes" });
    expect(within(replies).getAllByRole("article")).toHaveLength(2);
    expect(within(replies).getByRole("link", { name: "@Mark Cruz" })).toHaveAttribute("href", "#comment-2");
    // A direct reply to the top comment needs no name: the thread already says it.
    expect(within(replies).queryByRole("link", { name: "@Ana Reyes" })).not.toBeInTheDocument();

    await user.click(within(replies).getByRole("button", { name: "Reply to Lee Jasmin" }));
    await user.type(screen.getByRole("textbox", { name: "Reply to Lee Jasmin" }), "Welcome");
    await user.click(screen.getByRole("button", { name: "Post reply" }));
    await waitFor(() => expect(postComment).toHaveBeenCalledWith(RECORD_ID, { body: "Welcome", reply_to: 3 }));
  });

  it("starts a thread with more than two replies collapsed, and can open and close it", async () => {
    const user = userEvent.setup();
    setComments([onDay(1, 1), onDay(2, 2, { reply_to: 1 }), onDay(3, 3, { reply_to: 1 }), onDay(4, 4, { reply_to: 1 })]);
    renderComments();

    const open = await screen.findByRole("button", { name: "View 3 replies" });
    expect(screen.queryByText("Body 2")).not.toBeInTheDocument();
    await user.click(open);
    expect(screen.getByText("Body 2")).toBeInTheDocument();
    expect(screen.getByText("Body 4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hide replies" }));
    expect(screen.queryByText("Body 2")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View 3 replies" })).toBeInTheDocument();
  });

  it("shows up to two replies without asking", async () => {
    setComments([onDay(1, 1), onDay(2, 2, { reply_to: 1 }), onDay(3, 3, { reply_to: 1 })]);
    renderComments();

    expect(await screen.findByText("Body 3")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /View \d+ repl/ })).not.toBeInTheDocument();
  });

  it("scrolls to the comment an @name link points at", async () => {
    const user = userEvent.setup();
    const scroll = vi.fn();
    const original = window.HTMLElement.prototype.scrollIntoView;
    window.HTMLElement.prototype.scrollIntoView = scroll;
    try {
      setComments([onDay(1, 1), onDay(2, 2, { reply_to: 1 }), onDay(3, 3, { reply_to: 2 })]);
      renderComments();

      await user.click(await screen.findByRole("link", { name: "@Reader 2" }));
      expect(scroll).toHaveBeenCalled();
      expect(scroll.mock.instances[0]).toHaveProperty("id", "comment-2");
    } finally {
      window.HTMLElement.prototype.scrollIntoView = original;
    }
  });

  it("posts a comment, counting characters left only when few remain", async () => {
    const user = userEvent.setup();
    setComments([onDay(4, 4)]);
    renderComments();

    const field = await screen.findByRole("textbox", { name: "Add a comment" });
    expect(field).toHaveAttribute("maxLength", "2000");
    await user.type(field, "Hello paper readers");
    expect(screen.queryByText(/characters remaining/)).not.toBeInTheDocument();

    fireEvent.change(field, { target: { value: "x".repeat(1750) } });
    expect(screen.getByText("250 characters remaining")).toBeInTheDocument();

    fireEvent.change(field, { target: { value: "Hello paper readers" } });
    await user.click(screen.getByRole("button", { name: "Post comment" }));
    await waitFor(() => expect(postComment).toHaveBeenCalledWith(RECORD_ID, { body: "Hello paper readers" }));
    await waitFor(() => expect(field).toHaveValue(""));
  });

  it("posts with Ctrl+Enter and lets Enter add a line", async () => {
    const user = userEvent.setup();
    renderComments();

    const field = await screen.findByRole("textbox", { name: "Add a comment" });
    await user.type(field, "First line{Enter}Second line");
    expect(postComment).not.toHaveBeenCalled();
    expect(field).toHaveValue("First line\nSecond line");
    await user.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(postComment).toHaveBeenCalledWith(RECORD_ID, { body: "First line\nSecond line" }));
  });

  it("does not post an empty comment", async () => {
    renderComments();

    expect(await screen.findByRole("button", { name: "Post comment" })).toBeDisabled();
  });

  it("opens a reply under the comment being answered, and Escape closes it", async () => {
    const user = userEvent.setup();
    setComments([onDay(4, 4, { author_name: "Ana Reyes" })]);
    renderComments();

    await user.click(await screen.findByRole("button", { name: "Reply to Ana Reyes" }));
    const field = screen.getByRole("textbox", { name: "Reply to Ana Reyes" });
    expect(field).toHaveFocus();
    expect(screen.getByText("Replying to")).toBeInTheDocument();
    await user.type(field, "A reply");
    await user.click(screen.getByRole("button", { name: "Post reply" }));
    await waitFor(() => expect(postComment).toHaveBeenLastCalledWith(RECORD_ID, { body: "A reply", reply_to: 4 }));

    await user.click(await screen.findByRole("button", { name: "Reply to Ana Reyes" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("textbox", { name: "Reply to Ana Reyes" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reply to Ana Reyes" })).toHaveFocus();
  });

  it("opens the thread after a reply is posted into a collapsed one", async () => {
    const user = userEvent.setup();
    setComments([onDay(1, 1), onDay(2, 2, { reply_to: 1 }), onDay(3, 3, { reply_to: 1 }), onDay(4, 4, { reply_to: 1 })]);
    renderComments();

    await screen.findByRole("button", { name: "View 3 replies" });
    await user.click(screen.getByRole("button", { name: "Reply to Reader 1" }));
    expect(screen.getByText("Body 2")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Reply to Reader 1" })).toBeInTheDocument();
  });

  it("keeps Edit and Delete in the writer's menu and Report in everyone else's", async () => {
    const user = userEvent.setup();
    setComments([
      onDay(1, 1, { author_name: "Lee Reader", can_edit: true, can_report: false }),
      onDay(2, 2, { author_name: "Ana Reyes" }),
    ]);
    renderComments();

    const own = await screen.findByRole("button", { name: "More actions for Lee Reader's comment" });
    expect(own).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    await user.click(own);
    expect(own).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Report" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "More actions for Ana Reyes's comment" }));
    expect(screen.getByRole("button", { name: "Report" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("closes the menu on Escape, returning focus to its button, and on an outside click", async () => {
    const user = userEvent.setup();
    setComments([onDay(1, 1, { author_name: "Lee Reader", can_edit: true, can_report: false })]);
    renderComments();

    const trigger = await screen.findByRole("button", { name: "More actions for Lee Reader's comment" });
    await user.click(trigger);
    expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    await user.click(trigger);
    await user.click(screen.getByRole("heading", { name: /Comments/ }));
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("lets a writer edit in place and asks for confirmation before deleting", async () => {
    const user = userEvent.setup();
    setComments([onDay(5, 5, { author_name: "Lee Reader", body: "Old words", can_edit: true, can_report: false })]);
    renderComments();

    await user.click(await screen.findByRole("button", { name: "More actions for Lee Reader's comment" }));
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const field = screen.getByRole("textbox", { name: "Edit comment" });
    expect(field).toHaveValue("Old words");
    expect(field).toHaveFocus();
    await user.clear(field);
    await user.type(field, "Updated wording");
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    await waitFor(() => expect(editComment).toHaveBeenCalledWith(RECORD_ID, 5, { body: "Updated wording" }));
    expect(screen.queryByRole("textbox", { name: "Edit comment" })).not.toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "More actions for Lee Reader's comment" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.getByRole("dialog", { name: "Delete this comment?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete comment" }));
    await waitFor(() => expect(deleteComment).toHaveBeenCalledWith(RECORD_ID, 5));
  });

  it("cancels an edit with Escape and leaves the words alone", async () => {
    const user = userEvent.setup();
    setComments([onDay(5, 5, { author_name: "Lee Reader", body: "Old words", can_edit: true, can_report: false })]);
    renderComments();

    await user.click(await screen.findByRole("button", { name: "More actions for Lee Reader's comment" }));
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.type(screen.getByRole("textbox", { name: "Edit comment" }), " more");
    await user.keyboard("{Escape}");
    expect(screen.getByText("Old words")).toBeInTheDocument();
    expect(editComment).not.toHaveBeenCalled();
  });

  it("keeps a deleted comment's place when it has replies, without its text or name", async () => {
    setComments([
      gone(8, 1, "writer"),
      onDay(9, 2, { body: "Which part was this about?", reply_to: 8 }),
      gone(10, 3, "moderator"),
      onDay(11, 4, { body: "Answering the removed one", reply_to: 10 }),
    ]);
    renderComments();

    expect(await screen.findByText("[deleted]")).toBeInTheDocument();
    expect(screen.getByText("[removed]")).toBeInTheDocument();
    expect(screen.getByText("Which part was this about?")).toBeInTheDocument();
    expect(screen.queryByText("Ana Reyes")).not.toBeInTheDocument();
    // A deleted comment has no author to name, so a menu for it would read "More actions for 's comment".
    expect(screen.queryByRole("button", { name: "More actions for 's comment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Reply to $/ })).not.toBeInTheDocument();
  });

  it("hides a deleted comment that has nothing beneath it", async () => {
    setComments([gone(8, 1, "writer"), gone(9, 2, "moderator"), onDay(10, 3)]);
    renderComments();

    expect(await screen.findByText("Body 10")).toBeInTheDocument();
    expect(screen.queryByText("[deleted]")).not.toBeInTheDocument();
    expect(screen.queryByText("[removed]")).not.toBeInTheDocument();
  });

  it("submits report reasons and requires a note for Other", async () => {
    const user = userEvent.setup();
    setComments([onDay(10, 10)]);
    renderComments();

    await user.click(await screen.findByRole("button", { name: "More actions for Reader 10's comment" }));
    await user.click(screen.getByRole("button", { name: "Report" }));
    const dialog = await screen.findByRole("dialog", { name: "Report comment" });
    await user.click(within(dialog).getByLabelText("Other"));
    expect(within(dialog).getByRole("button", { name: "Submit report" })).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox", { name: "Note" }), "This does not belong here");
    await user.click(within(dialog).getByRole("button", { name: "Submit report" }));
    await waitFor(() => expect(reportComment).toHaveBeenCalledWith(RECORD_ID, 10, { reason: "other", note: "This does not belong here" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Comment reported");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("cuts a long comment and shows the rest on request", async () => {
    const user = userEvent.setup();
    const long = `${"word ".repeat(70)}the very end`;
    setComments([onDay(1, 1, { body: long })]);
    renderComments();

    expect(screen.queryByText(/the very end/)).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "See more" }));
    expect(screen.getByText(/the very end/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "See more" })).not.toBeInTheDocument();
  });

  it("sorts oldest first and can show the newest first", async () => {
    const user = userEvent.setup();
    setComments([onDay(2, 2), onDay(3, 3), onDay(1, 1)]);
    renderComments();

    await screen.findByRole("list", { name: "Comments" });
    expect(topLevelBodies().map((text) => text.match(/Body \d/)?.[0])).toEqual(["Body 1", "Body 2", "Body 3"]);
    await user.selectOptions(screen.getByRole("combobox", { name: "Sort by" }), "newest");
    expect(topLevelBodies().map((text) => text.match(/Body \d/)?.[0])).toEqual(["Body 3", "Body 2", "Body 1"]);
  });

  it("shows five top-level comments at a time", async () => {
    const user = userEvent.setup();
    setComments([1, 2, 3, 4, 5, 6, 7].map((id) => onDay(id, id)));
    renderComments();

    await screen.findByRole("list", { name: "Comments" });
    expect(topLevelBodies()).toHaveLength(5);
    await user.click(screen.getByRole("button", { name: "View 2 more comments" }));
    expect(topLevelBodies()).toHaveLength(7);
    expect(screen.queryByRole("button", { name: /more comment/ })).not.toBeInTheDocument();
  });

  it("shows the server's error message", async () => {
    const user = userEvent.setup();
    postComment.mockRejectedValueOnce({ response: { status: 400, data: { detail: "Comments are limited to 2,000 characters." } } });
    renderComments();

    await user.type(await screen.findByRole("textbox", { name: "Add a comment" }), "A comment");
    await user.click(screen.getByRole("button", { name: "Post comment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Comments are limited to 2,000 characters.");
  });

  it("is read-only for signed-out readers", async () => {
    setComments([onDay(1, 1, { author_name: "Ana Reyes" })]);
    renderComments(null);

    expect(await screen.findByText("Body 1")).toBeInTheDocument();
    expect(screen.getByText("Sign in to join the discussion.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Add a comment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Reply/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /More actions for/ })).not.toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations", async () => {
    setComments([
      onDay(1, 1, { is_author: true }),
      onDay(2, 2, { reply_to: 1, can_edit: true, can_report: false }),
      onDay(3, 3, { reply_to: 2 }),
      gone(4, 4),
      onDay(5, 5, { reply_to: 4 }),
    ]);
    const { container } = renderComments();

    await screen.findByRole("list", { name: "Comments" });
    await expectNoBlockingA11yViolations(container);
  });
});
