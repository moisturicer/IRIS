/**
 * The reviewer's side of document requests (IR-262, IR-263; ADR-022 §3.4, §4).
 *
 * One block, shared by the reviewer page and the paper view: the Request
 * documents control, and the open requests the viewer's party made, with
 * Withdraw. A sent document is supplied, with no Accept or Reject (ADR-022
 * Amendment 10, IR-1338; these tests changed deliberately with it). Whether
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
const withdrawDocumentRequest = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    documentRequests: (id: number) => documentRequests(id),
    withdrawDocumentRequest: (id: number) => withdrawDocumentRequest(id),
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
    id: 1, party: "ierc", label: "IERC", state: "open", state_label: "Open",
    message: "The signed consent forms are missing.", requested_by: "Ivy Ethics",
    created_at: "2026-09-20T02:00:00Z", closed_at: null,
    can_manage: true,
    items: [item(), item({ id: 12, label: "Protocol", state: "missing", state_label: "Missing", upload: null, uploaded_at: null })],
    ...overrides,
  };
}

function signInAs(roleName: string) {
  useAuthStore.setState({
    user: { id: 2, role_name: roleName } as never,
    isAuthenticated: true,
  } as never);
}

function renderBlock(canRequest: Party[] = [], onChanged = vi.fn(), reviewing = true) {
  return renderScreen(
    <ReviewerDocumentRequests
      reviewing={reviewing}
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
  withdrawDocumentRequest.mockResolvedValue({ data: request({ state: "withdrawn" }) });
});

describe("ReviewerDocumentRequests", () => {
  it("offers Request documents when the API names a party", async () => {
    documentRequests.mockResolvedValue({ data: [] });
    renderBlock(["ierc"]);

    expect(await screen.findByRole("button", { name: "Request documents" })).toBeInTheDocument();
  });

  it("says a request waits for Finish review once the dialog adds it", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    documentRequests.mockResolvedValue({ data: [] });
    renderBlock(["ierc"], onChanged);

    await user.click(await screen.findByRole("button", { name: "Request documents" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByRole("checkbox", { name: "Ethics Clearance" }));
    await user.type(within(dialog).getByRole("textbox", { name: /message to the owner/i }), "Missing.");
    await user.click(within(dialog).getByRole("button", { name: /add to review/i }));

    // A draft until the reviewer finishes (ADR-022 Amendment 9, IR-1325).
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Added to your review. It is sent when you finish your review with Request changes or Comment only.");
    expect(onChanged).toHaveBeenCalled();
  });

  it("lists what the viewer's party asked for, a sent document as Supplied", async () => {
    renderBlock();

    const region = await yourRequest();
    expect(within(region).getByText("The signed consent forms are missing.")).toBeInTheDocument();
    const [consent, protocol] = within(region).getAllByRole("listitem");
    expect(consent).toHaveTextContent("Consent form");
    expect(consent).toHaveTextContent("Supplied");
    expect(protocol).toHaveTextContent("Protocol");
    expect(protocol).toHaveTextContent("Requested");
  });

  it("offers no Accept or Reject on a supplied document", async () => {
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

  it("withdraws an open request once confirmed, asking no reason", async () => {
    const user = userEvent.setup();
    documentRequests.mockResolvedValue({
      data: [request({
        state: "open", state_label: "Open",
        items: [item({ state: "missing", state_label: "Missing", upload: null })],
      })],
    });
    renderBlock();

    await user.click(await screen.findByRole("button", { name: "Withdraw request" }));
    // IR-263 records no withdrawal reason; IR-270 defines any it needs.
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm withdrawal" }));

    await waitFor(() => expect(withdrawDocumentRequest).toHaveBeenCalledWith(1));
  });

  it("lists no request whose documents were all supplied: it needs nothing more", async () => {
    documentRequests.mockResolvedValue({
      data: [request({ state: "fulfilled", state_label: "Fulfilled", items: [item()] })],
    });
    const { container } = renderBlock();

    await waitFor(() => expect(documentRequests).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Withdraw request" })).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows no request the viewer's party did not make, and none that needs nothing", async () => {
    documentRequests.mockResolvedValue({
      data: [
        request({ can_manage: false }),
        request({ id: 2, state: "withdrawn", state_label: "Withdrawn" }),
        request({ id: 3, state: "fulfilled", state_label: "Fulfilled", items: [item({ state: "accepted", state_label: "Accepted" })] }),
      ],
    });
    const { container } = renderBlock();

    await waitFor(() => expect(documentRequests).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: "Documents you requested" })).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  // Whether the viewer reviews comes from the capabilities adapter now, not
  // from their role (IR-411), so the caller says so.
  it("does not load requests for a viewer who reviews nothing", async () => {
    renderBlock([], vi.fn(), false);

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
