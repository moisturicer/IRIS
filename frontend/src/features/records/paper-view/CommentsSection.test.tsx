import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "@/api/records";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
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

let current: PublicCommentsResponse;
let loadComments: ReturnType<typeof vi.spyOn>;
let postComment: ReturnType<typeof vi.spyOn>;
let editComment: ReturnType<typeof vi.spyOn>;
let deleteComment: ReturnType<typeof vi.spyOn>;
let reportComment: ReturnType<typeof vi.spyOn>;

function renderComments(viewerId: number | null = VIEWER_ID) {
  return renderScreen(<CommentsSection recordId={RECORD_ID} viewerId={viewerId} />);
}

beforeEach(() => {
  current = { comments: [], count: 0 };
  loadComments = vi.spyOn(recordsApi, "publicComments").mockImplementation(async () => ({ data: current } as never));
  postComment = vi.spyOn(recordsApi, "postPublicComment").mockResolvedValue({ data: comment() } as never);
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

  it("renders a flat oldest-first thread with author, edited, and reply links", async () => {
    current = {
      count: 2,
      comments: [
        comment({ id: 2, author_name: "Lee Reader", body: "A reply", created_at: "2026-11-02T09:00:00Z", edited_at: "2026-11-02T10:00:00Z", is_author: true, reply_to: 1, can_edit: true, can_report: false }),
        comment({ id: 1, body: "First comment" }),
      ],
    };
    renderComments();

    expect(await screen.findByRole("heading", { name: "Comments (2)" })).toBeInTheDocument();
    const rows = await screen.findAllByRole("listitem");
    expect(within(rows[0]).getByText("First comment")).toBeInTheDocument();
    expect(within(rows[1]).getByText("A reply")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Author")).toBeInTheDocument();
    expect(within(rows[1]).getByText("edited")).toBeInTheDocument();
    expect(within(rows[1]).getByRole("link", { name: "Ana Reyes" })).toHaveAttribute("href", "#comment-1");
  });

  it("posts plain text and a reply with a remaining-character counter", async () => {
    const user = userEvent.setup();
    current = { count: 1, comments: [comment({ id: 4 })] };
    renderComments();

    const field = await screen.findByRole("textbox", { name: "Add a comment" });
    expect(field).toHaveAttribute("maxLength", "2000");
    await user.type(field, "Hello paper readers");
    expect(screen.getByText("1981 characters remaining")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Post comment" }));
    await waitFor(() => expect(postComment).toHaveBeenCalledWith(RECORD_ID, { body: "Hello paper readers" }));

    await user.click(await screen.findByRole("button", { name: "Reply" }));
    await user.type(screen.getByRole("textbox", { name: "Add a comment" }), "A reply");
    await user.click(screen.getByRole("button", { name: "Post reply" }));
    await waitFor(() => expect(postComment).toHaveBeenLastCalledWith(RECORD_ID, { body: "A reply", reply_to: 4 }));
  });

  it("lets a writer edit and asks for confirmation before deleting", async () => {
    const user = userEvent.setup();
    current = { count: 1, comments: [comment({ id: 5, author_name: "Current Reader", body: "Old words", can_edit: true, can_report: false })] };
    renderComments();

    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const field = screen.getByRole("textbox", { name: "Edit comment" });
    await user.clear(field);
    await user.type(field, "Updated wording");
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    await waitFor(() => expect(editComment).toHaveBeenCalledWith(RECORD_ID, 5, { body: "Updated wording" }));

    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(screen.getByRole("dialog", { name: "Delete this comment?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete comment" }));
    await waitFor(() => expect(deleteComment).toHaveBeenCalledWith(RECORD_ID, 5));
  });

  it("shows deleted and removed markers without exposing text or names", async () => {
    current = {
      count: 0,
      comments: [
        comment({ id: 8, author_name: null, body: null, deletion_kind: "writer", can_report: false }),
        comment({ id: 9, author_name: null, body: null, deletion_kind: "moderator", can_report: false }),
      ],
    };
    renderComments();

    expect(await screen.findByText("[deleted]")).toBeInTheDocument();
    expect(screen.getByText("[removed]")).toBeInTheDocument();
    expect(screen.queryByText("Ana Reyes")).not.toBeInTheDocument();
    expect(screen.queryByText("A useful paper.")).not.toBeInTheDocument();
  });

  it("submits report reasons and requires a note for Other", async () => {
    const user = userEvent.setup();
    current = { count: 1, comments: [comment({ id: 10 })] };
    renderComments();

    await user.click(await screen.findByRole("button", { name: "Report" }));
    const dialog = await screen.findByRole("dialog", { name: "Report comment" });
    await user.click(within(dialog).getByLabelText("Other"));
    expect(within(dialog).getByRole("button", { name: "Submit report" })).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox", { name: "Note" }), "This does not belong here");
    await user.click(within(dialog).getByRole("button", { name: "Submit report" }));
    await waitFor(() => expect(reportComment).toHaveBeenCalledWith(RECORD_ID, 10, { reason: "other", note: "This does not belong here" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Comment reported");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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
    current = { count: 1, comments: [comment()] };
    renderComments(null);

    expect(await screen.findByText("A useful paper.")).toBeInTheDocument();
    expect(screen.getByText("Sign in to join the discussion.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Add a comment" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reply" })).not.toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderComments();

    await screen.findByRole("heading", { name: "Comments (0)" });
    await expectNoBlockingA11yViolations(container);
  });
});
