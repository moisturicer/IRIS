/**
 * IR-688: RDCO's download-request queue shows the reader's note and each
 * grant's expiry, asks for a note on decline and revoke, and offers Revoke only
 * on a grant the server says is still live (ADR-048, decisions 4 and 7).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { useUIStore } from "@/store/ui.store";
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
  useUIStore.setState({ toasts: [] });
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

describe("paging (IR-1100)", () => {
  const first = request({ id: 1, record_title: "First page paper" });
  const second = request({ id: 2, record_title: "Second page paper" });

  /** A server with more than one page of requests. */
  function twoPages() {
    listDownloadRequests.mockImplementation((params: { page?: number }) =>
      Promise.resolve({
        data: params.page === 2
          ? { results: [second], next: null }
          : { results: [first], next: "http://api/records/download-requests/?page=2" },
      }),
    );
  }

  it("offers Load more when the server has another page, and appends it", async () => {
    twoPages();
    renderScreen(<DownloadRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("link", { name: "Second page paper" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "First page paper" })).toBeInTheDocument();
    expect(listDownloadRequests.mock.calls.at(-1)?.[0]).toEqual({ status: "pending", page: 2 });
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(screen.getByText("2 requests")).toBeInTheDocument();
  });

  it("shows no Load more when everything fits on one page", async () => {
    listDownloadRequests.mockResolvedValue({ data: { results: [first], next: null } });
    renderScreen(<DownloadRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });

    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(screen.getByText("1 request")).toBeInTheDocument();
  });

  it("starts again from the first page when the filter changes", async () => {
    twoPages();
    renderScreen(<DownloadRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByRole("link", { name: "Second page paper" });

    await userEvent.click(screen.getByRole("button", { name: "Approved" }));

    await waitFor(() => expect(listDownloadRequests.mock.calls.at(-1)?.[0]).toEqual({ status: "approved" }));
    expect(await screen.findByRole("button", { name: "Load more" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Second page paper" })).not.toBeInTheDocument();
  });

  it("cancels the read in flight when the filter changes, so a stale page never replaces a newer one", async () => {
    const signals: AbortSignal[] = [];
    listDownloadRequests.mockImplementation((_params: unknown, options?: { signal?: AbortSignal }) => {
      if (!options?.signal) throw new Error("a read was made without an abort signal");
      signals.push(options.signal);
      return new Promise(() => undefined);
    });
    renderScreen(<DownloadRequestsPage />);
    await waitFor(() => expect(signals).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Declined" }));

    await waitFor(() => expect(signals).toHaveLength(2));
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it("says so when the next page cannot be read, and keeps what is shown", async () => {
    listDownloadRequests.mockImplementation((params: { page?: number }) =>
      params.page === 2
        ? Promise.reject(new Error("boom"))
        : Promise.resolve({ data: { results: [first], next: "http://api/?page=2" } }),
    );
    renderScreen(<DownloadRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load more/i);
    expect(screen.getByRole("link", { name: "First page paper" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load more" })).toBeInTheDocument();
  });
});

describe("approving (IR-1028)", () => {
  const toasts = () => useUIStore.getState().toasts;

  async function openApprove() {
    const trigger = within(await rowFor("A published thesis")).getByRole("button", { name: "Approve" });
    await userEvent.click(trigger);
    return { trigger, dialog: await screen.findByRole("dialog", { name: /Approve .*download/i }) };
  }

  it("asks in a dialog that names the reader and the paper, never the browser's confirm", async () => {
    const nativeConfirm = vi.spyOn(window, "confirm");
    serve(request({ id: 6 }));
    renderScreen(<DownloadRequestsPage />);

    const { dialog } = await openApprove();

    expect(dialog).toHaveTextContent("Ana Reyes");
    expect(dialog).toHaveTextContent("A published thesis");
    expect(dialog).toHaveTextContent(/in-app and by email/i);
    await expectNoBlockingA11yViolations(dialog);
    expect(nativeConfirm).not.toHaveBeenCalled();
    expect(approveDownloadRequest).not.toHaveBeenCalled();
    nativeConfirm.mockRestore();
  });

  it("does nothing on Cancel, and returns focus to the button that opened it", async () => {
    serve(request({ id: 6 }));
    renderScreen(<DownloadRequestsPage />);

    const { trigger, dialog } = await openApprove();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(approveDownloadRequest).not.toHaveBeenCalled();
    expect(listDownloadRequests).toHaveBeenCalledTimes(1);
    expect(toasts()).toHaveLength(0);
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("approves once on confirm, says so in a toast and reads the queue again", async () => {
    serve(request({ id: 6 }));
    approveDownloadRequest.mockResolvedValue({});
    renderScreen(<DownloadRequestsPage />);

    const { dialog } = await openApprove();
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve request" }));

    await waitFor(() => expect(approveDownloadRequest).toHaveBeenCalledTimes(1));
    expect(approveDownloadRequest).toHaveBeenCalledWith(6);
    await waitFor(() => expect(toasts()).toEqual([
      expect.objectContaining({ type: "success", message: expect.stringContaining("Ana Reyes") }),
    ]));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(listDownloadRequests).toHaveBeenCalledTimes(2));
  });

  it("disables the buttons and labels the confirm while the approval is in flight", async () => {
    serve(request({ id: 6 }));
    let finish: () => void = () => undefined;
    approveDownloadRequest.mockReturnValue(new Promise<void>((resolve) => { finish = resolve; }));
    renderScreen(<DownloadRequestsPage />);

    const { dialog } = await openApprove();
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve request" }));

    expect(await within(dialog).findByRole("button", { name: "Please wait…" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(approveDownloadRequest).toHaveBeenCalledTimes(1);
    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the server's reason in an error toast when the approval is refused", async () => {
    serve(request({ id: 6 }));
    approveDownloadRequest.mockRejectedValue({
      response: { status: 409, data: { detail: "This request was already decided." } },
    });
    renderScreen(<DownloadRequestsPage />);

    const { dialog } = await openApprove();
    await userEvent.click(within(dialog).getByRole("button", { name: "Approve request" }));

    await waitFor(() => expect(toasts()).toEqual([
      expect.objectContaining({ type: "error", message: "This request was already decided." }),
    ]));
    expect(listDownloadRequests).toHaveBeenCalledTimes(1);
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
