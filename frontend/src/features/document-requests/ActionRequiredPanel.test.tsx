/**
 * The owner's "Action required" panel on the paper view (IR-262, ADR-022 §3).
 *
 * Each open document request says who asked, why, and what is still missing,
 * with an upload control per item. The message is the reviewer's own words and
 * is shown as text, never as markup. Every query goes through the accessible
 * tree, by role and accessible name.
 */
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { DocumentRequest } from "@/types/records";

import { ActionRequiredPanel } from "./ActionRequiredPanel";

const documentRequests = vi.fn();
const uploadForRequestItem = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: { documentRequests: (id: number) => documentRequests(id) },
}));
vi.mock("@/api/documents", () => ({
  documentsApi: {
    uploadForRequestItem: (recordId: number, itemId: number, file: File) =>
      uploadForRequestItem(recordId, itemId, file),
  },
}));

const RECORD_ID = 9;

function request(overrides: Partial<DocumentRequest> = {}): DocumentRequest {
  return {
    id: 1,
    party: "ierc",
    label: "IERC",
    state: "open",
    state_label: "Open",
    message: "The signed consent forms are missing.",
    requested_by: "Ivy Ethics",
    created_at: "2026-09-20T02:00:00Z",
    closed_at: null, can_manage: false,
    items: [
      {
        id: 11, slot: 3, label: "Ethics Clearance", state: "missing",
        state_label: "Missing", upload: null, uploaded_at: null, rejection_reason: null, decided_at: null,
      },
      {
        id: 12, slot: null, label: "Consent form", state: "uploaded",
        state_label: "Uploaded", upload: 40, uploaded_at: "2026-09-21T02:00:00Z", rejection_reason: null, decided_at: null,
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  documentRequests.mockReset();
  uploadForRequestItem.mockReset().mockResolvedValue({ data: {} });
});

describe("ActionRequiredPanel", () => {
  it("lists an open request naming who asked, their message and each item", async () => {
    documentRequests.mockResolvedValue({ data: [request()] });
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    const panel = await screen.findByRole("region", { name: "Action required" });
    expect(within(panel).getByRole("heading", { name: /IERC requested documents/ })).toBeInTheDocument();
    expect(within(panel).getByText("The signed consent forms are missing.")).toBeInTheDocument();

    const items = within(panel).getByRole("list", { name: /documents requested by IERC/i });
    const [missing, uploaded] = within(items).getAllByRole("listitem");
    expect(missing).toHaveTextContent("Ethics Clearance");
    expect(missing).toHaveTextContent("Missing");
    expect(uploaded).toHaveTextContent("Consent form");
    expect(uploaded).toHaveTextContent("Uploaded");
  });

  it("offers an upload only for a missing item", async () => {
    documentRequests.mockResolvedValue({ data: [request()] });
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    expect(await screen.findByLabelText("Upload Ethics Clearance")).toBeInTheDocument();
    expect(screen.queryByLabelText("Upload Consent form")).not.toBeInTheDocument();
  });

  it("uploads against the item and shows it as uploaded", async () => {
    const user = userEvent.setup();
    documentRequests
      .mockResolvedValueOnce({ data: [request()] })
      .mockResolvedValueOnce({
        data: [request({
          items: request().items.map((i) => ({
            ...i, state: "uploaded" as const, state_label: "Uploaded",
          })),
        })],
      });
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    const file = new File(["%PDF-1.4"], "ethics.pdf", { type: "application/pdf" });
    await user.upload(await screen.findByLabelText("Upload Ethics Clearance"), file);

    await waitFor(() => expect(uploadForRequestItem).toHaveBeenCalledWith(RECORD_ID, 11, file));
    await waitFor(() =>
      expect(screen.queryByLabelText("Upload Ethics Clearance")).not.toBeInTheDocument(),
    );
    const items = screen.getByRole("list", { name: /documents requested by IERC/i });
    expect(within(items).getAllByRole("listitem")[0]).toHaveTextContent("Uploaded");
  });

  it("shows the request as fulfilled once the last item is uploaded", async () => {
    const user = userEvent.setup();
    const single = request({ items: [request().items[0]] });
    documentRequests
      .mockResolvedValueOnce({ data: [single] })
      .mockResolvedValueOnce({
        data: [{
          ...single,
          state: "fulfilled",
          state_label: "Fulfilled",
          items: [{ ...single.items[0], state: "uploaded", state_label: "Uploaded" }],
        }],
      });
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    const file = new File(["%PDF-1.4"], "ethics.pdf", { type: "application/pdf" });
    await user.upload(await screen.findByLabelText("Upload Ethics Clearance"), file);

    const panel = await screen.findByRole("region", { name: "Requested documents" });
    expect(within(panel).getByText(/fulfilled/i)).toBeInTheDocument();
    expect(within(panel).getByText(/IERC has been told/)).toBeInTheDocument();
    expect(within(panel).queryByLabelText(/^Upload/)).not.toBeInTheDocument();
  });

  it("says when an upload fails", async () => {
    const user = userEvent.setup();
    documentRequests.mockResolvedValue({ data: [request()] });
    uploadForRequestItem.mockRejectedValue({
      response: { data: { detail: "Only PDF files are accepted." } },
    });
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    const file = new File(["x"], "ethics.pdf", { type: "application/pdf" });
    await user.upload(await screen.findByLabelText("Upload Ethics Clearance"), file);

    expect(await screen.findByRole("alert")).toHaveTextContent("Only PDF files are accepted.");
  });

  it("renders the message as text, never as markup", async () => {
    documentRequests.mockResolvedValue({
      data: [request({ message: "<b>Bold</b> <img src=x onerror=alert(1)>" })],
    });
    const { container } = renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    expect(
      await screen.findByText("<b>Bold</b> <img src=x onerror=alert(1)>"),
    ).toBeInTheDocument();
    // Structural queries on purpose, and the one exception to querying the
    // accessibility tree: what is proved here is that the message produced
    // *no* elements, and an absent <b> or <img> has no role or name to find.
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows nothing when no request is open", async () => {
    documentRequests.mockResolvedValue({
      data: [request({ state: "fulfilled", state_label: "Fulfilled" })],
    });
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    await waitFor(() => expect(documentRequests).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: "Action required" })).not.toBeInTheDocument();
  });

  it("shows the owner why an upload was rejected, with the upload offered again", async () => {
    documentRequests.mockResolvedValue({
      data: [request({
        items: [{
          ...request().items[0],
          rejection_reason: "The scan is unreadable; please rescan at 300 dpi.",
          decided_at: "2026-09-22T02:00:00Z",
        }],
      })],
    });
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    const panel = await screen.findByRole("region", { name: "Action required" });
    const [row] = within(panel).getAllByRole("listitem");
    expect(row).toHaveTextContent(
      "IERC did not accept your last upload: “The scan is unreadable; please rescan at 300 dpi.”",
    );
    expect(within(row).getByLabelText("Upload Ethics Clearance")).toBeInTheDocument();
  });

  it("drops a withdrawn request", async () => {
    documentRequests.mockResolvedValue({
      data: [request({ state: "withdrawn", state_label: "Withdrawn" })],
    });
    const { container } = renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    await waitFor(() => expect(documentRequests).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("says so when the requests cannot be loaded, instead of showing nothing", async () => {
    documentRequests.mockRejectedValue(new Error("Network Error"));
    renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not load the documents reviewers asked for/i,
    );
  });

  it("has no blocking accessibility violations", async () => {
    documentRequests.mockResolvedValue({ data: [request()] });
    const { container } = renderScreen(<ActionRequiredPanel recordId={RECORD_ID} />);

    await screen.findByRole("region", { name: "Action required" });
    await expectNoBlockingA11yViolations(container);
  });
});
