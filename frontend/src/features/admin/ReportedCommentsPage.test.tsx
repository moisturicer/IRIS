/**
 * The Reported comments page (IR-693): RDCO and the System Admin read every
 * comment with an open report, then remove it with a reason or dismiss its
 * reports (ADR-032 §7, amendment 2026-10-31; decisions 2026-11-15). Queried
 * through the accessible tree only.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { moderationApi } from "@/api/moderation";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { useUIStore } from "@/store/ui.store";
import * as queueCounts from "@/lib/queueCounts";
import type { ReportedComment } from "@/types/records";

import ReportedCommentsPage from "./ReportedCommentsPage";

function row(overrides: Partial<ReportedComment> = {}): ReportedComment {
  return {
    id: 41,
    record: { id: 7, title: "Solar dryers for rural farms" },
    author_name: "Ana Cruz",
    reported_texts: ["Buy cheap followers at example.test"],
    current_text: "Buy cheap followers at example.test",
    deletion_kind: null,
    report_count: 2,
    reasons: [{ reason: "spam", count: 1 }, { reason: "other", count: 1 }],
    notes: ["It names a student."],
    first_reported_at: "2026-11-14T09:00:00Z",
    ...overrides,
  };
}

let listed: ReportedComment[];
let list: ReturnType<typeof vi.spyOn>;
let remove: ReturnType<typeof vi.spyOn>;
let dismiss: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  useUIStore.setState({ toasts: [] });
  listed = [row()];
  list = vi.spyOn(moderationApi, "reportedComments").mockImplementation(async () => ({ data: { comments: listed } } as never));
  remove = vi.spyOn(moderationApi, "removeComment").mockResolvedValue({ data: undefined } as never);
  dismiss = vi.spyOn(moderationApi, "dismissReports").mockResolvedValue({ data: undefined } as never);
});

afterEach(() => vi.restoreAllMocks());

const render = () => renderScreen(<ReportedCommentsPage />);

describe("the queue", () => {
  it("shows what was reported, on which paper, why and how often", async () => {
    const { container } = render();

    const item = await screen.findByRole("article", { name: /Ana Cruz's comment/ });
    expect(within(item).getByRole("link", { name: "Solar dryers for rural farms" })).toHaveAttribute("href", "/records/7");
    expect(item).toHaveTextContent("Buy cheap followers at example.test");
    expect(item).toHaveTextContent("2 reports");
    expect(within(item).getByText("Spam 1")).toBeInTheDocument();
    expect(within(item).getByText("Other 1")).toBeInTheDocument();
    expect(item).toHaveTextContent("It names a student.");
    await expectNoBlockingA11yViolations(container);
  });

  it("shows the wording now beside the wording reported, when the writer edited it", async () => {
    listed = [row({ current_text: "Sorry, wrong thread." })];
    render();

    const item = await screen.findByRole("article", { name: /Ana Cruz's comment/ });
    expect(item).toHaveTextContent("As reported");
    expect(item).toHaveTextContent("Now reads");
    expect(item).toHaveTextContent("Sorry, wrong thread.");
  });

  it("says so when nothing waits", async () => {
    listed = [];
    render();

    expect(await screen.findByText("No reported comments")).toBeInTheDocument();
  });

  it("does not mistake a failed read for an empty queue", async () => {
    list.mockRejectedValue(new Error("down"));
    render();

    expect(await screen.findByRole("alert")).toHaveTextContent(/reported comments didn't load/i);
    expect(screen.queryByText("No reported comments")).not.toBeInTheDocument();
  });
});

describe("acting on a comment", () => {
  it("removes it with a reason the writer is told, then reads the queue again", async () => {
    const user = userEvent.setup();
    const changed = vi.spyOn(queueCounts, "queueCountsChanged");
    render();

    await user.click(await screen.findByRole("button", { name: "Remove Ana Cruz's comment" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove comment" });
    expect(within(dialog).getByRole("button", { name: "Remove" })).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox", { name: "Note to the writer" }), "Advertising.");
    listed = [];
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith(41, "Advertising."));
    expect(await screen.findByText("No reported comments")).toBeInTheDocument();
    expect(useUIStore.getState().toasts[0]).toMatchObject({ type: "success", message: "Comment removed. Its writer was told why." });
    expect(changed).toHaveBeenCalled();
  });

  it("dismisses the reports and leaves the comment", async () => {
    const user = userEvent.setup();
    render();

    listed = [];
    await user.click(await screen.findByRole("button", { name: "Dismiss reports on Ana Cruz's comment" }));

    await waitFor(() => expect(dismiss).toHaveBeenCalledWith(41));
    expect(await screen.findByText("No reported comments")).toBeInTheDocument();
    expect(useUIStore.getState().toasts[0]).toMatchObject({ type: "success", message: "Reports dismissed. The comment stays." });
  });

  it("says someone else got there first, and reads the queue again", async () => {
    const user = userEvent.setup();
    dismiss.mockRejectedValue({ response: { status: 409, data: { detail: "This comment's reports were already handled." } } });
    render();

    listed = [];
    await user.click(await screen.findByRole("button", { name: "Dismiss reports on Ana Cruz's comment" }));

    await waitFor(() => expect(useUIStore.getState().toasts[0]).toMatchObject({
      type: "error", message: "This comment's reports were already handled.",
    }));
    expect(await screen.findByText("No reported comments")).toBeInTheDocument();
  });

  it("offers only Dismiss on a comment its writer already deleted", async () => {
    listed = [row({ current_text: null, deletion_kind: "writer" })];
    render();

    const item = await screen.findByRole("article", { name: /Ana Cruz's comment/ });
    expect(item).toHaveTextContent("Deleted by its writer");
    expect(within(item).queryByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
    expect(within(item).getByRole("button", { name: /^Dismiss/ })).toBeInTheDocument();
  });
});
