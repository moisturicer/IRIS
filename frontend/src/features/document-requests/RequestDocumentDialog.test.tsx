/**
 * The reviewer's "Request documents" dialog (IR-262, ADR-022 §2).
 *
 * The reviewer ticks documents from the record type's upload slots, or names
 * one under "Other", and says why. Every query goes through the accessible
 * tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor } from "@/test/render";

import { RequestDocumentDialog } from "./RequestDocumentDialog";

const documentRequestSlots = vi.fn();
const createDocumentRequest = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    documentRequestSlots: (id: number) => documentRequestSlots(id),
    createDocumentRequest: (id: number, body: unknown) => createDocumentRequest(id, body),
  },
}));

const RECORD_ID = 7;

function open(parties: Array<"ierc" | "intake" | "rdco"> = ["ierc"]) {
  const onClose = vi.fn();
  const onCreated = vi.fn();
  renderScreen(
    <RequestDocumentDialog
      recordId={RECORD_ID}
      parties={parties}
      partyLabels={{ ierc: "IERC", intake: "Intake & Triage", rdco: "RDCO Final" }}
      onClose={onClose}
      onCreated={onCreated}
    />,
  );
  return { onClose, onCreated };
}

beforeEach(() => {
  documentRequestSlots.mockReset().mockResolvedValue({
    data: [
      { id: 3, name: "Ethics Clearance" },
      { id: 4, name: "Patent Draft" },
    ],
  });
  createDocumentRequest.mockReset().mockResolvedValue({ data: { id: 1 } });
});

describe("RequestDocumentDialog", () => {
  it("is a labelled dialog listing the record type's documents", async () => {
    open();

    expect(screen.getByRole("dialog", { name: "Request documents" })).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "Ethics Clearance" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Patent Draft" })).toBeInTheDocument();
    expect(documentRequestSlots).toHaveBeenCalledWith(RECORD_ID);
  });

  it("sends the ticked documents, an Other item and the message", async () => {
    const user = userEvent.setup();
    const { onCreated } = open();

    await user.click(await screen.findByRole("checkbox", { name: "Ethics Clearance" }));
    await user.type(screen.getByRole("textbox", { name: /other document/i }), "Rescanned consent form");
    await user.type(
      screen.getByRole("textbox", { name: /message to the owner/i }),
      "The signed consent forms are missing.",
    );
    await user.click(screen.getByRole("button", { name: "Send request" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(createDocumentRequest).toHaveBeenCalledWith(RECORD_ID, {
      message: "The signed consent forms are missing.",
      items: [{ slot: 3 }, { label: "Rescanned consent form" }],
    });
  });

  it("refuses to send with no document chosen", async () => {
    const user = userEvent.setup();
    open();

    await screen.findByRole("checkbox", { name: "Ethics Clearance" });
    await user.type(screen.getByRole("textbox", { name: /message to the owner/i }), "Why");
    await user.click(screen.getByRole("button", { name: "Send request" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/choose at least one document/i);
    expect(createDocumentRequest).not.toHaveBeenCalled();
  });

  it("refuses to send without a message", async () => {
    const user = userEvent.setup();
    open();

    await user.click(await screen.findByRole("checkbox", { name: "Patent Draft" }));
    await user.click(screen.getByRole("button", { name: "Send request" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/tell the owner why/i);
    expect(createDocumentRequest).not.toHaveBeenCalled();
  });

  it("shows the server's refusal", async () => {
    const user = userEvent.setup();
    createDocumentRequest.mockRejectedValue({
      response: { data: { detail: "You do not hold this record." } },
    });
    open();

    await user.click(await screen.findByRole("checkbox", { name: "Patent Draft" }));
    await user.type(screen.getByRole("textbox", { name: /message to the owner/i }), "Why");
    await user.click(screen.getByRole("button", { name: "Send request" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("You do not hold this record.");
  });

  it("asks which party to act as when the reviewer holds two", async () => {
    const user = userEvent.setup();
    open(["intake", "rdco"]);

    const asParty = screen.getByRole("combobox", { name: /asking as/i });
    await user.selectOptions(asParty, "RDCO Final");
    await user.click(await screen.findByRole("checkbox", { name: "Patent Draft" }));
    await user.type(screen.getByRole("textbox", { name: /message to the owner/i }), "Why");
    await user.click(screen.getByRole("button", { name: "Send request" }));

    await waitFor(() =>
      expect(createDocumentRequest).toHaveBeenCalledWith(RECORD_ID, {
        message: "Why",
        items: [{ slot: 4 }],
        party: "rdco",
      }),
    );
  });

  it("closes on Cancel", async () => {
    const user = userEvent.setup();
    const { onClose } = open();

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalled();
  });

  it("has no blocking accessibility violations", async () => {
    const { container } = renderScreen(
      <RequestDocumentDialog
        recordId={RECORD_ID}
        parties={["ierc"]}
        partyLabels={{ ierc: "IERC" }}
        onClose={() => {}}
        onCreated={() => {}}
      />,
    );
    await screen.findByRole("checkbox", { name: "Ethics Clearance" });
    await expectNoBlockingA11yViolations(container);
  });
});
