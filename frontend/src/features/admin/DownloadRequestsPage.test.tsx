/**
 * IR-688: RDCO's download-request queue shows the reader's note and each
 * grant's expiry, asks for a note on decline and revoke, and offers Revoke only
 * on a grant the server says is still live (ADR-048, decisions 4 and 7).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { DownloadRequest } from "@/types/records";

import DownloadRequestsPage from "./DownloadRequestsPage";

const listDownloadRequests = vi.fn();
const approveDownloadRequest = vi.fn();
const declineDownloadRequest = vi.fn();
const revokeDownloadRequest = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    listDownloadRequests: (...args: unknown[]) => listDownloadRequests(...args),
    approveDownloadRequest: (...args: unknown[]) => approveDownloadRequest(...args),
    declineDownloadRequest: (...args: unknown[]) => declineDownloadRequest(...args),
    revokeDownloadRequest: (...args: unknown[]) => revokeDownloadRequest(...args),
  },
}));

function request(overrides: Partial<DownloadRequest>): DownloadRequest {
  return {
    id: 1,
    record: 7,
    record_title: "A published thesis",
    requested_by: 3,
    requested_by_name: "Ana Reyes",
    requested_by_email: "ana@cit.edu",
    note: "I am citing its survey method.",
    status: "pending",
    rdco_note: "",
    reviewed_by: null,
    reviewed_at: null,
    grant_expires_at: null,
    grant_live: false,
    revoked_at: null,
    cancelled_at: null,
    created_at: "2026-10-30T08:00:00Z",
    ...overrides,
  };
}

function serve(...rows: DownloadRequest[]) {
  listDownloadRequests.mockResolvedValue({ data: { results: rows } });
}

async function rowFor(title: string) {
  return (await screen.findByRole("link", { name: title })).closest("tr") as HTMLElement;
}

beforeEach(() => {
  listDownloadRequests.mockReset();
  approveDownloadRequest.mockReset();
  declineDownloadRequest.mockReset();
  revokeDownloadRequest.mockReset();
});

describe("the queue", () => {
  it("keeps Refresh on its own phone row and restores the compact toolbar placement from sm (IR-772)", () => {
    serve();
    renderScreen(<DownloadRequestsPage />);

    const refresh = screen.getByRole("button", { name: "Refresh" });
    expect(refresh).toHaveClass(
      "w-full",
      "justify-center",
      "sm:ml-auto",
      "sm:w-auto",
    );
  });

  it("shows the reader's note, and says so when an old request has none", async () => {
    serve(
      request({ id: 1 }),
      request({ id: 2, record_title: "An older thesis", note: "" }),
    );
    const { container } = renderScreen(<DownloadRequestsPage />);

    expect(within(await rowFor("A published thesis")).getByText("I am citing its survey method.")).toBeInTheDocument();
    expect(within(await rowFor("An older thesis")).getByText("No note recorded")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows a grant's expiry and offers Revoke only while it is live", async () => {
    serve(
      request({ id: 1, status: "approved", grant_expires_at: "2026-11-29T08:00:00Z", grant_live: true }),
      request({
        id: 2, record_title: "An expired grant", status: "approved",
        grant_expires_at: "2026-10-01T08:00:00Z", grant_live: false,
      }),
    );
    renderScreen(<DownloadRequestsPage />);

    const live = await rowFor("A published thesis");
    expect(within(live).getByText(/Until 29 Nov 2026/)).toBeInTheDocument();
    expect(within(live).getByRole("button", { name: "Revoke" })).toBeInTheDocument();

    const expired = await rowFor("An expired grant");
    expect(within(expired).getByText(/Expired 1 Oct 2026/)).toBeInTheDocument();
    expect(within(expired).queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
  });

  it("shows RDCO's note on a declined or revoked request", async () => {
    serve(
      request({ id: 1, status: "declined", rdco_note: "Ask your adviser." }),
      request({ id: 2, record_title: "A revoked grant", status: "revoked", rdco_note: "Shared outside CIT-U." }),
      request({ id: 3, record_title: "An old decline", status: "declined", rdco_note: "" }),
    );
    renderScreen(<DownloadRequestsPage />);

    expect(within(await rowFor("A published thesis")).getByText("Ask your adviser.")).toBeInTheDocument();
    expect(within(await rowFor("A revoked grant")).getByText("Shared outside CIT-U.")).toBeInTheDocument();
    expect(within(await rowFor("An old decline")).getByText("No note recorded")).toBeInTheDocument();
  });
});

describe("declining and revoking", () => {
  it("asks for a note before declining, and sends it", async () => {
    serve(request({ id: 4 }));
    declineDownloadRequest.mockResolvedValue({});
    renderScreen(<DownloadRequestsPage />);

    await userEvent.click(within(await rowFor("A published thesis")).getByRole("button", { name: "Decline" }));
    const dialog = await screen.findByRole("dialog", { name: "Decline download request" });
    await expectNoBlockingA11yViolations(dialog);

    const send = within(dialog).getByRole("button", { name: "Decline" });
    expect(send).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Note to the reader" }), " Ask your adviser. ");
    await userEvent.click(send);

    await waitFor(() => expect(declineDownloadRequest).toHaveBeenCalledWith(4, "Ask your adviser."));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("asks for a note before revoking, and keeps it when the server refuses", async () => {
    serve(request({ id: 5, status: "approved", grant_expires_at: "2026-11-29T08:00:00Z", grant_live: true }));
    revokeDownloadRequest.mockRejectedValue({
      response: { data: { detail: "Only an approved, unexpired grant can be revoked." } },
    });
    renderScreen(<DownloadRequestsPage />);

    await userEvent.click(within(await rowFor("A published thesis")).getByRole("button", { name: "Revoke" }));
    const dialog = await screen.findByRole("dialog", { name: "Revoke download access" });
    const note = within(dialog).getByRole("textbox", { name: "Note to the reader" });
    expect(note).toHaveAttribute("maxLength", "500");
    await userEvent.type(note, "Shared outside CIT-U.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Revoke" }));

    await waitFor(() => expect(revokeDownloadRequest).toHaveBeenCalledWith(5, "Shared outside CIT-U."));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Only an approved, unexpired grant can be revoked.",
    );
    expect(note).toHaveValue("Shared outside CIT-U.");
  });
});
