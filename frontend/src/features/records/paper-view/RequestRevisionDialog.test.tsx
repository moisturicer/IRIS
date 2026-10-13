/**
 * *Request Revision* (IR-272, ADR-032 §5), with IR-143's two carried
 * criteria: a refusal keeps the typed reason beside the server's, and
 * closing the dialog to read a document loses nothing. Every query goes
 * through the accessible tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor } from "@/test/render";
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

beforeEach(() => {
  sessionStorage.clear();
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

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("A revision request from IERC is already open.");
    expect(alert).toHaveTextContent("Your reason is kept.");
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

    expect(readRevisionDraft(7)).toBe("");
  });
});
