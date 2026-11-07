/**
 * *Clear* and *Record finding* (IR-269, ADR-032 §3–§4), with IR-143's two
 * carried criteria: a refusal keeps the typed comment beside the server's
 * reason, and closing the dialog to read a document loses nothing. Every
 * query goes through the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { useAuthStore } from "@/store/auth.store";
import { renderScreen, screen, waitFor } from "@/test/render";
import type { User } from "@/types/auth";
import type { OfficeReviewOutcome, RecordDetail } from "@/types/records";

import { OfficeReviewDialog } from "./OfficeReviewDialog";
import { readOfficeReviewDraft } from "./officeReviewDraft";

const officeReview = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    officeReview: (id: number, body: unknown) => officeReview(id, body),
  },
}));

const RECORD = {
  id: 7,
  office_review: { party: "ierc", label: "IERC", blocked: null, assignment: 31 },
} as unknown as RecordDetail;

function open(outcome: OfficeReviewOutcome) {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderScreen(
    <OfficeReviewDialog record={RECORD} outcome={outcome} onClose={onClose} onDone={onDone} />,
  );
  return { onClose, onDone, view };
}

/** The signed-in user; null is nobody signed in. */
function signInAs(id: number | null) {
  useAuthStore.setState({ user: id === null ? null : ({ id } as User) });
}

beforeEach(() => {
  sessionStorage.clear();
  signInAs(1);
  officeReview.mockReset().mockResolvedValue({ data: {} });
});

describe("OfficeReviewDialog", () => {
  it("clears with no comment needed, and says the office decides when it finishes", async () => {
    const { onDone, view } = open("cleared");

    expect(screen.getByRole("dialog", { name: "Clear for IERC" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Comment (optional)" })).not.toBeRequired();
    await expectNoBlockingA11yViolations(view.container);

    await userEvent.click(screen.getByRole("button", { name: "Clear" }));

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Cleared for IERC."));
    expect(officeReview).toHaveBeenCalledWith(7, { outcome: "cleared", comment: "" });
  });

  it("will not record a finding without its reason", async () => {
    const { onDone } = open("finding");

    const button = screen.getByRole("button", { name: "Record finding" });
    expect(button).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "What is the finding?" })).toBeRequired();

    await userEvent.type(screen.getByRole("textbox", { name: "What is the finding?" }), "  Consent forms omit minors. ");
    await userEvent.click(button);

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Finding recorded for IERC."));
    expect(officeReview).toHaveBeenCalledWith(7, { outcome: "finding", comment: "Consent forms omit minors." });
  });

  it("offers no way to reject or publish", () => {
    open("finding");
    expect(screen.queryByRole("button", { name: /reject|publish/i })).not.toBeInTheDocument();
  });

  it("keeps the typed comment beside the server's reason when the record moved", async () => {
    officeReview.mockRejectedValue({
      response: { data: { detail: "IERC is no longer reviewing this record." } },
    });
    const { onDone } = open("finding");
    const box = screen.getByRole("textbox", { name: "What is the finding?" });
    await userEvent.type(box, "Sampling frame is unclear.");

    await userEvent.click(screen.getByRole("button", { name: "Record finding" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("IERC is no longer reviewing this record.");
    expect(alert).toHaveTextContent("Your comment is kept.");
    expect(box).toHaveValue("Sampling frame is unclear.");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("keeps the comment when the dialog is closed to read a document, and forgets it once recorded", async () => {
    const first = open("finding");
    await userEvent.type(screen.getByRole("textbox", { name: "What is the finding?" }), "Missing assent forms.");
    first.view.unmount();

    // Reopened after reading the paper: the comment is still there.
    open("finding");
    const box = screen.getByRole("textbox", { name: "What is the finding?" });
    expect(box).toHaveValue("Missing assent forms.");
    await userEvent.click(screen.getByRole("button", { name: "Record finding" }));
    await waitFor(() => expect(officeReview).toHaveBeenCalled());

    // Recorded: the next dialog on this record starts empty.
    expect(readOfficeReviewDraft(1, 7, "finding")).toBe("");
  });

  it("never offers a finding's draft as a clearance's note", async () => {
    const first = open("finding");
    await userEvent.type(screen.getByRole("textbox", { name: "What is the finding?" }), "Not my clearance.");
    first.view.unmount();

    open("cleared");
    expect(screen.getByRole("textbox", { name: "Comment (optional)" })).toHaveValue("");
  });

  describe("drafts belong to the signed-in user (IR-931)", () => {
    const finding = () => screen.getByRole("textbox", { name: "What is the finding?" });

    it("does not show A's unsent finding to B on the same tab, and gives it back to A", async () => {
      signInAs(1);
      const first = open("finding");
      await userEvent.type(finding(), "A's unsent finding.");
      first.view.unmount();

      signInAs(2);
      const asB = open("finding");
      expect(finding()).toHaveValue("");
      asB.view.unmount();

      // Back after an idle expiry: nothing was cleared on the way out.
      signInAs(1);
      open("finding");
      expect(finding()).toHaveValue("A's unsent finding.");
    });

    it("keeps B's record of a finding from touching A's draft", async () => {
      signInAs(1);
      const first = open("finding");
      await userEvent.type(finding(), "A's unsent finding.");
      first.view.unmount();

      signInAs(2);
      open("finding");
      expect(finding()).toHaveValue("");
      await userEvent.type(finding(), "B's finding.");
      await userEvent.click(screen.getByRole("button", { name: "Record finding" }));
      await waitFor(() => expect(officeReview).toHaveBeenCalled());

      expect(readOfficeReviewDraft(2, 7, "finding")).toBe("");
      expect(readOfficeReviewDraft(1, 7, "finding")).toBe("A's unsent finding.");
    });

    it("reads and writes nothing with nobody signed in, and ignores the old unkeyed key", async () => {
      sessionStorage.setItem("iris_office_review_draft:7:finding", "From before the change.");
      signInAs(null);
      const none = open("finding");
      expect(finding()).toHaveValue("");

      await userEvent.type(finding(), "Nobody's draft.");
      expect(Object.keys(sessionStorage)).toEqual(["iris_office_review_draft:7:finding"]);
      expect(sessionStorage.getItem("iris_office_review_draft:7:finding")).toBe("From before the change.");
      none.view.unmount();

      // Signed in, the old key is not picked up either.
      signInAs(1);
      open("finding");
      expect(finding()).toHaveValue("");
    });
  });
});
