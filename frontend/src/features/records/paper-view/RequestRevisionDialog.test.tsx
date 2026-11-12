/**
 * *Request Revision* (IR-272, ADR-032 §5), with IR-143's two carried
 * criteria: a refusal keeps the typed reason beside the server's, and
 * closing the dialog to read a document loses nothing. Every query goes
 * through the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore } from "@/store/ui.store";
import { renderScreen, screen, waitFor } from "@/test/render";
import type { User } from "@/types/auth";
import type { RecordDetail } from "@/types/records";

import { RequestRevisionDialog } from "./RequestRevisionDialog";
import { readRevisionDraft } from "./revisionDraft";

const requestRevision = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    requestRevision: (id: number, body: unknown) => requestRevision(id, body),
  },
}));

const RECORD = {
  id: 7,
  revision: { party: "ierc", label: "IERC", blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  versions: [{ number: 1 }, { number: 2 }],
} as unknown as RecordDetail;

function open() {
  const onClose = vi.fn();
  const onDone = vi.fn();
  const view = renderScreen(<RequestRevisionDialog record={RECORD} onClose={onClose} onDone={onDone} />);
  return { onClose, onDone, view };
}

const reasonBox = () => screen.getByRole("textbox", { name: "What needs revising?" });

/** The signed-in user; null is nobody signed in. */
function signInAs(id: number | null) {
  useAuthStore.setState({ user: id === null ? null : ({ id } as User) });
}

beforeEach(() => {
  useUIStore.setState({ toasts: [] });
  sessionStorage.clear();
  signInAs(1);
  requestRevision.mockReset().mockResolvedValue({ data: {} });
});

describe("RequestRevisionDialog", () => {
  it("keeps the retired review form's words and names the version being reviewed", async () => {
    const { view } = open();

    const dialog = screen.getByRole("dialog", { name: "Request Revision" });
    expect(dialog).toHaveTextContent("Send back to the owner for changes. They may resubmit after revising.");
    expect(reasonBox()).toHaveAccessibleDescription(/against v2, the version you reviewed/);
    await expectNoBlockingA11yViolations(view.container);
  });

  it("will not send without a reason, and sends it trimmed", async () => {
    const { onDone } = open();

    const send = screen.getByRole("button", { name: "Request Revision" });
    expect(send).toBeDisabled();
    expect(reasonBox()).toBeRequired();

    await userEvent.type(reasonBox(), "  Add the assent form for minors. ");
    await userEvent.click(send);

    await waitFor(() => expect(onDone).toHaveBeenCalledWith("Revision requested. The owner has been notified."));
    expect(requestRevision).toHaveBeenCalledWith(7, { reason: "Add the assent form for minors." });
  });

  it("keeps the typed reason beside the server's when the record moved", async () => {
    requestRevision.mockRejectedValue({
      response: { data: { detail: "A revision request from IERC is already open." } },
    });
    const { onDone } = open();
    await userEvent.type(reasonBox(), "Sampling frame is unclear.");

    await userEvent.click(screen.getByRole("button", { name: "Request Revision" }));

    // A toast (it floats and can be dismissed), never a line that grows the dialog.
    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    const [toast] = useUIStore.getState().toasts;
    expect(toast.type).toBe("error");
    // Long enough that it may not be read in four seconds: stays until X.
    expect(toast.persist).toBe(true);
    expect(toast.message).toContain("A revision request from IERC is already open.");
    expect(toast.message).toContain("Your reason is kept.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(reasonBox()).toHaveValue("Sampling frame is unclear.");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("keeps the reason when the dialog is closed to read a document, and forgets it once sent", async () => {
    const first = open();
    await userEvent.type(reasonBox(), "Missing assent forms.");
    first.view.unmount();

    open();
    expect(reasonBox()).toHaveValue("Missing assent forms.");
    await userEvent.click(screen.getByRole("button", { name: "Request Revision" }));
    await waitFor(() => expect(requestRevision).toHaveBeenCalled());

    expect(readRevisionDraft(1, 7)).toBe("");
  });

  describe("drafts belong to the signed-in user (IR-931)", () => {
    it("does not show A's unsent reason to B on the same tab, and gives it back to A", async () => {
      signInAs(1);
      const first = open();
      await userEvent.type(reasonBox(), "A's unsent reason.");
      first.view.unmount();

      signInAs(2);
      const asB = open();
      expect(reasonBox()).toHaveValue("");
      asB.view.unmount();

      // Back after an idle expiry: nothing was cleared on the way out.
      signInAs(1);
      open();
      expect(reasonBox()).toHaveValue("A's unsent reason.");
    });

    it("keeps B's request from touching A's draft", async () => {
      signInAs(1);
      const first = open();
      await userEvent.type(reasonBox(), "A's unsent reason.");
      first.view.unmount();

      signInAs(2);
      open();
      expect(reasonBox()).toHaveValue("");
      await userEvent.type(reasonBox(), "B's reason.");
      await userEvent.click(screen.getByRole("button", { name: "Request Revision" }));
      await waitFor(() => expect(requestRevision).toHaveBeenCalled());

      expect(readRevisionDraft(2, 7)).toBe("");
      expect(readRevisionDraft(1, 7)).toBe("A's unsent reason.");
    });

    it("reads and writes nothing with nobody signed in, and ignores the old unkeyed key", async () => {
      sessionStorage.setItem("iris_revision_draft:7", "From before the change.");
      signInAs(null);
      const none = open();
      expect(reasonBox()).toHaveValue("");

      await userEvent.type(reasonBox(), "Nobody's draft.");
      expect(Object.keys(sessionStorage)).toEqual(["iris_revision_draft:7"]);
      expect(sessionStorage.getItem("iris_revision_draft:7")).toBe("From before the change.");
      none.view.unmount();

      // Signed in, the old key is not picked up either.
      signInAs(1);
      open();
      expect(reasonBox()).toHaveValue("");
    });
  });
});
