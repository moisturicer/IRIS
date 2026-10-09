/**
 * The three Decisions (IR-270, ADR-032 §3): *Accept & publish*, *Keep
 * unlisted* and *Reject*, with IR-143's two carried criteria -- a stale
 * submit shows a notice, keeps the typed comment and never decides into the
 * changed record, and closing the dialog to read a document loses nothing.
 * Every query goes through the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { DecisionFlags, DecisionOutcome, RecordDetail } from "@/types/records";

import { DecisionDialog } from "./DecisionDialog";
import { readDecisionDraft } from "./decisionDraft";

const decide = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    decide: (id: number, body: unknown) => decide(id, body),
  },
}));

const ADVISER: DecisionFlags = {
  party: "adviser",
  outcomes: ["publish", "reject"],
  blocked: null,
  closes: { assignments: [], document_requests: 0 },
  token: "t1",
  author_hints: ["The author flagged possible intellectual property."],
};

const RDCO: DecisionFlags = {
  party: "rdco",
  outcomes: ["publish", "keep_unlisted", "reject"],
  blocked: null,
  closes: {
    assignments: [{ party: "ierc", label: "IERC", holders: ["Elena Reyes"] }],
    document_requests: 1,
  },
  token: "t1",
  author_hints: [],
};

function recordWith(decision: DecisionFlags, type = "Thesis / Research"): RecordDetail {
  return { id: 7, record_type_name: type, decision } as unknown as RecordDetail;
}

function open(outcome: DecisionOutcome, decision: DecisionFlags = ADVISER, type?: string) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderScreen(
    <DecisionDialog record={recordWith(decision, type)} outcome={outcome} onClose={onClose} onDone={onDone} />,
  );
  return { onClose, onDone, view };
}

beforeEach(() => {
  sessionStorage.clear();
  decide.mockReset().mockResolvedValue({ data: {} });
});

describe("DecisionDialog", () => {
  it("asks the Adviser to publish without specialist review, showing the author's flags", async () => {
    const { onDone, view } = open("publish");

    const dialog = screen.getByRole("dialog", { name: "Publish without specialist review?" });
    expect(dialog).toHaveTextContent("This publishes the thesis to Discover. No office will review it.");
    expect(within(dialog).getByRole("list", { name: "The author flagged" })).toHaveTextContent(
      "The author flagged possible intellectual property.",
    );
    expect(screen.getByRole("textbox", { name: "Comment (optional)" })).not.toBeRequired();
    await expectNoBlockingA11yViolations(view.container);

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Published. It is now in Discover."));
    expect(decide).toHaveBeenCalledWith(7, { outcome: "publish", comment: "", token: "t1" });
  });

  it("names a project as a project", () => {
    open("publish", ADVISER, "Project");
    expect(screen.getByRole("dialog")).toHaveTextContent("This publishes the project to Discover.");
  });

  it("tells RDCO what deciding closes", () => {
    open("publish", RDCO);

    const dialog = screen.getByRole("dialog", { name: "Publish this thesis?" });
    const closes = within(dialog).getByRole("list", { name: "This also closes" });
    expect(closes).toHaveTextContent("IERC's review in progress (Elena Reyes)");
    expect(closes).toHaveTextContent("1 open document request");
    expect(within(dialog).queryByRole("list", { name: "The author flagged" })).not.toBeInTheDocument();
  });

  it("says keeping a record unlisted cannot yet be undone", async () => {
    const { onDone } = open("keep_unlisted", RDCO);

    const dialog = screen.getByRole("dialog", { name: "Accept and keep unlisted?" });
    expect(dialog).toHaveTextContent("It stays out of Discover and Ask IRIS");
    expect(dialog).toHaveTextContent("Publishing it later is not yet possible in IRIS.");
    await userEvent.click(screen.getByRole("button", { name: "Keep unlisted" }));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Accepted and kept unlisted."));
  });

  it("will not reject without a reason", async () => {
    const { onDone } = open("reject");

    expect(screen.getByRole("dialog", { name: "Reject and archive?" })).toHaveTextContent(
      "The owner cannot submit a new version",
    );
    const button = screen.getByRole("button", { name: "Reject and archive" });
    expect(button).toBeDisabled();
    const box = screen.getByRole("textbox", { name: "Why is it rejected?" });
    expect(box).toBeRequired();

    await userEvent.type(box, "  It duplicates a 2023 thesis. ");
    await userEvent.click(button);

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Rejected. The record is archived."));
    expect(decide).toHaveBeenCalledWith(7, {
      outcome: "reject", comment: "It duplicates a 2023 thesis.", token: "t1",
    });
  });

  it("on a stale record shows what it would now close, keeps the text, and decides only when asked again", async () => {
    decide.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: "This record changed while you were deciding.",
          decision: { ...RDCO, token: "t2", closes: { assignments: [{ party: "ktto", label: "KTTO", holders: [] }], document_requests: 0 } },
        },
      },
    });
    const { onDone } = open("reject", RDCO);
    const box = screen.getByRole("textbox", { name: "Why is it rejected?" });
    await userEvent.type(box, "Out of scope.");

    await userEvent.click(screen.getByRole("button", { name: "Reject and archive" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This record changed while you were deciding.");
    expect(alert).toHaveTextContent("Your reason is kept.");
    expect(box).toHaveValue("Out of scope.");
    expect(onDone).not.toHaveBeenCalled();
    const closes = screen.getByRole("list", { name: "This also closes" });
    expect(closes).toHaveTextContent("KTTO's review, not yet claimed");
    expect(closes).not.toHaveTextContent("IERC");

    // Deciding again uses the fresh token: never the one the dialog opened with.
    await userEvent.click(screen.getByRole("button", { name: "Reject and archive" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(decide).toHaveBeenLastCalledWith(7, { outcome: "reject", comment: "Out of scope.", token: "t2" });
  });

  it("keeps the text when closed to read a document, per outcome, and forgets it once decided", async () => {
    const first = open("reject");
    await userEvent.type(screen.getByRole("textbox", { name: "Why is it rejected?" }), "Plagiarised section 3.");
    first.view.unmount();

    // A reject's reason never turns up as a publish comment.
    const publish = open("publish");
    expect(screen.getByRole("textbox", { name: "Comment (optional)" })).toHaveValue("");
    publish.view.unmount();

    open("reject");
    expect(screen.getByRole("textbox", { name: "Why is it rejected?" })).toHaveValue("Plagiarised section 3.");
    await userEvent.click(screen.getByRole("button", { name: "Reject and archive" }));
    await waitFor(() => expect(decide).toHaveBeenCalled());

    expect(readDecisionDraft(7, "reject")).toBe("");
  });
});
