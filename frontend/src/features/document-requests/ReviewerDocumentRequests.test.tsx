/**
 * The reviewer's side of document requests (IR-262, IR-263; ADR-022 §3.4, §4).
 *
 * One block, shared by the reviewer page and the paper view: the Request
 * documents control, and the requests the viewer's party made, with Accept
 * and Reject on each uploaded item and Withdraw on an open request. Whether
 * the viewer may manage a request is the server's `can_manage`; the controls
 * follow it. Every query goes through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import { useAuthStore } from "@/store/auth.store";
import type { DocumentRequest, DocumentRequestItem, Party } from "@/types/records";

import { ReviewerDocumentRequests } from "./ReviewerDocumentRequests";

const documentRequests = vi.fn();
const decideDocumentRequestItem = vi.fn();
const withdrawDocumentRequest = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    documentRequests: (id: number) => documentRequests(id),
    decideDocumentRequestItem: (id: number, body: unknown) => decideDocumentRequestItem(id, body),
    withdrawDocumentRequest: (id: number, reason?: string) => withdrawDocumentRequest(id, reason),
    documentRequestSlots: () => Promise.resolve({ data: [{ id: 3, name: "Ethics Clearance" }] }),
    createDocumentRequest: () => Promise.resolve({ data: {} }),
  },
}));

const RECORD_ID = 9;

function item(overrides: Partial<DocumentRequestItem> = {}): DocumentRequestItem {
  return {
    id: 11, slot: null, label: "Consent form", state: "uploaded", state_label: "Uploaded",
    upload: 40, uploaded_at: "2026-09-21T02:00:00Z", rejection_reason: null, decided_at: null,
    ...overrides,
  };
}

function request(overrides: Partial<DocumentRequest> = {}): DocumentRequest {
  return {
    id: 1, party: "ierc", label: "IERC", state: "fulfilled", state_label: "Fulfilled",
    message: "The signed consent forms are missing.", requested_by: "Ivy Ethics",
    created_at: "2026-09-20T02:00:00Z", closed_at: "2026-09-21T02:00:00Z",
    withdrawal_reason: null, can_manage: true, items: [item()],
    ...overrides,
  };
}

function signInAs(roleName: string) {
  useAuthStore.setState({
    user: { id: 2, role_name: roleName } as never,
    isAuthenticated: true,
  } as never);
}

function renderBlock(canRequest: Party[] = [], onChanged = vi.fn()) {
  return renderScreen(
    <ReviewerDocumentRequests
      record={{
        id: RECORD_ID,
        can_request_document: canRequest,
        current_holders: [{ party: "ierc", label: "IERC", opened_at: null, opened_by: null }],
      }}
      onChanged={onChanged}
    />,
  );
}

async function yourRequest() {
  return screen.findByRole("region", { name: "Documents you requested" });
}

beforeEach(() => {
  vi.clearAllMocks();
  signInAs("IERC");
  documentRequests.mockResolvedValue({ data: [request()] });
  decideDocumentRequestItem.mockResolvedValue({ data: request() });
  withdrawDocumentRequest.mockResolvedValue({ data: request({ state: "withdrawn" }) });
});

describe("ReviewerDocumentRequests", () => {
  it("offers Request documents when the API names a party", async () => {
    documentRequests.mockResolvedValue({ data: [] });
    renderBlock(["ierc"]);

    expect(await screen.findByRole("button", { name: "Request documents" })).toBeInTheDocument();
  });

  it("confirms a request once the dialog sends it", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    documentRequests.mockResolvedValue({ data: [] });
    renderBlock(["ierc"], onChanged);

    await user.click(await screen.findByRole("button", { name: "Request documents" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("checkbox", { name: "Ethics Clearance" }));
    await user.type(within(dialog).getByRole("textbox", { name: /message to the owner/i }), "Missing.");
    await user.click(within(dialog).getByRole("button", { name: /send request/i }));

    expect(await screen.findByRole("status")).toHaveTextContent("Documents requested.");
    expect(onChanged).toHaveBeenCalled();
  });

  it("lists what the viewer's party asked for, with each item's state", async () => {
    renderBlock();

    const region = await yourRequest();
    expect(within(region).getByText("The signed consent forms are missing.")).toBeInTheDocument();
    const [row] = within(region).getAllByRole("listitem");
    expect(row).toHaveTextContent("Consent form");
    expect(row).toHaveTextContent("Uploaded");
  });

  it("accepts an uploaded item", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    renderBlock([], onChanged);

    await user.click(await screen.findByRole("button", { name: "Accept Consent form" }));

    await waitFor(() =>
      expect(decideDocumentRequestItem).toHaveBeenCalledWith(11, { action: "accept" }),
    );
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("rejects only with a reason, and sends it", async () => {
    const user = userEvent.setup();
    renderBlock();

    await user.click(await screen.findByRole("button", { name: "Reject Consent form" }));
    const reason = screen.getByRole("textbox", { name: /why is consent form not acceptable/i });
    const send = screen.getByRole("button", { name: "Send rejection" });
    expect(send).toBeDisabled();

    await user.type(reason, "Unreadable scan.");
    await user.click(send);

    await waitFor(() =>
      expect(decideDocumentRequestItem).toHaveBeenCalledWith(11, {
        action: "reject", reason: "Unreadable scan.",
      }),
    );
  });

  it("offers no decision on an item that is not uploaded", async () => {
    documentRequests.mockResolvedValue({
      data: [request({
        state: "open", state_label: "Open",
        items: [
          item({ state: "missing", state_label: "Missing", upload: null, uploaded_at: null }),
          item({ id: 12, label: "Protocol", state: "accepted", state_label: "Accepted" }),
        ],
      })],
    });
    renderBlock();

    await yourRequest();
    expect(screen.queryByRole("button", { name: /^Accept/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Reject/ })).not.toBeInTheDocument();
  });

  it("shows the reason it gave on a rejected item", async () => {
    documentRequests.mockResolvedValue({
      data: [request({
        state: "open", state_label: "Open",
        items: [item({
          state: "missing", state_label: "Missing", upload: null,
          rejection_reason: "Unreadable scan.",
        })],
      })],
    });
    renderBlock();

    const region = await yourRequest();
    expect(within(region).getByText(/Unreadable scan\./)).toBeInTheDocument();
  });

  it("withdraws an open request, with an optional reason", async () => {
    const user = userEvent.setup();
    documentRequests.mockResolvedValue({
      data: [request({
        state: "open", state_label: "Open",
        items: [item({ state: "missing", state_label: "Missing", upload: null })],
      })],
    });
    renderBlock();

    await user.click(await screen.findByRole("button", { name: "Withdraw request" }));
    await user.type(screen.getByRole("textbox", { name: /reason/i }), "Found it.");
    await user.click(screen.getByRole("button", { name: "Confirm withdrawal" }));

    await waitFor(() => expect(withdrawDocumentRequest).toHaveBeenCalledWith(1, "Found it."));
  });

  it("offers no withdrawal on a request that is already closed", async () => {
    renderBlock();

    await yourRequest();
    expect(screen.queryByRole("button", { name: "Withdraw request" })).not.toBeInTheDocument();
  });

  it("says why a decision was refused", async () => {
    const user = userEvent.setup();
    decideDocumentRequestItem.mockRejectedValue({
      response: { data: { detail: "That request was withdrawn." } },
    });
    renderBlock();

    await user.click(await screen.findByRole("button", { name: "Accept Consent form" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("That request was withdrawn.");
  });

  it("shows no request the viewer's party did not make, and none that needs nothing", async () => {
    documentRequests.mockResolvedValue({
      data: [
        request({ can_manage: false }),
        request({ id: 2, state: "withdrawn", state_label: "Withdrawn" }),
        request({ id: 3, items: [item({ state: "accepted", state_label: "Accepted" })] }),
      ],
    });
    const { container } = renderBlock();

    await waitFor(() => expect(documentRequests).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: "Documents you requested" })).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("does not load requests for a viewer who reviews nothing", async () => {
    signInAs("Student");
    renderBlock();

    expect(documentRequests).not.toHaveBeenCalled();
  });

  it("stays quiet when the viewer may not read the requests", async () => {
    documentRequests.mockRejectedValue({ response: { status: 403 } });
    const { container } = renderBlock();

    await waitFor(() => expect(documentRequests).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("has no blocking accessibility violations", async () => {
    const { container } = renderBlock(["ierc"]);

    await yourRequest();
    await expectNoBlockingA11yViolations(container);
  });
});
