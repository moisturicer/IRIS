/**
 * IR-914: RDCO's delete-request queue reads under `useApiRead`. A timed-out
 * read is the "interrupted" state with a Retry, a change of filter cancels the
 * read in flight, and the reader's Retry is the only thing that repeats it.
 *
 * IR-1076 (audit WF-02): Pending and Decided are the two tabs. Pending asks for
 * pending requests and offers the action; Decided asks for the rest, shows each
 * outcome and the requester's reason, and offers no action.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import type { DeleteRequest } from "@/types/records";

import DeleteRequestsPage from "./DeleteRequestsPage";

const listDeleteRequests = vi.fn();

vi.mock("@/api/records", () => ({
  recordsApi: {
    listDeleteRequests: (...args: unknown[]) => listDeleteRequests(...args),
    approveDeleteRequest: vi.fn(),
  },
}));

function request(overrides: Partial<DeleteRequest>): DeleteRequest {
  return {
    id: 1,
    record: 7,
    record_title: "A withdrawn thesis",
    requested_by: 3,
    requested_by_name: "Ana Reyes",
    requested_by_email: "ana@cit.edu",
    reason: "Duplicate upload",
    status: "pending",
    created_at: "2026-10-30T08:00:00Z",
    reviewed_by: null,
    reviewed_at: null,
    ...overrides,
  };
}

/** The signal a read was given, failing the test if a read was made without one. */
function readSignal(options?: { signal?: AbortSignal }): AbortSignal {
  if (!options?.signal) throw new Error("a read was made without an abort signal");
  return options.signal;
}

beforeEach(() => {
  listDeleteRequests.mockReset();
});

describe("DeleteRequestsPage reads", () => {
  it("shows a timed-out read as interrupted, and Retry reads again", async () => {
    listDeleteRequests
      .mockRejectedValueOnce(new RequestTimeoutError(30_000, "get", "/records/delete-requests/"))
      .mockResolvedValueOnce({ data: { results: [request({})] } });

    renderScreen(<DeleteRequestsPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/did not finish|took too long/i);
    expect(listDeleteRequests).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByRole("link", { name: "A withdrawn thesis" })).toBeInTheDocument();
    expect(listDeleteRequests).toHaveBeenCalledTimes(2);
  });

  it("cancels the read in flight when the filter changes", async () => {
    const signals: AbortSignal[] = [];
    listDeleteRequests.mockImplementation((_params: unknown, options?: { signal?: AbortSignal }) => {
      signals.push(readSignal(options));
      return new Promise(() => undefined);
    });

    renderScreen(<DeleteRequestsPage />);
    await waitFor(() => expect(signals).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Decided" }));

    await waitFor(() => expect(signals).toHaveLength(2));
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it("cancels the read when the screen unmounts", async () => {
    const signals: AbortSignal[] = [];
    listDeleteRequests.mockImplementation((_params: unknown, options?: { signal?: AbortSignal }) => {
      signals.push(readSignal(options));
      return new Promise(() => undefined);
    });

    const { unmount } = renderScreen(<DeleteRequestsPage />);
    await waitFor(() => expect(signals).toHaveLength(1));

    unmount();

    expect(signals[0].aborted).toBe(true);
  });
});

describe("DeleteRequestsPage tabs (IR-1076)", () => {
  const waiting = request({ id: 1, record_title: "Still waiting", status: "pending" });
  const turnedDown = request({
    id: 2,
    record_title: "Turned down",
    status: "declined",
    reason: "Kept for the archive",
    reviewed_at: "2026-11-02T08:00:00Z",
  });
  const removed = request({
    id: 3,
    record_title: "Removed thesis",
    status: "approved",
    reason: "Duplicate upload",
    reviewed_at: "2026-11-03T08:00:00Z",
  });

  it("opens on Pending, asks for pending requests and offers the action", async () => {
    listDeleteRequests.mockResolvedValue({ data: { results: [waiting] } });

    renderScreen(<DeleteRequestsPage />);

    expect(await screen.findByRole("link", { name: "Still waiting" })).toBeInTheDocument();
    expect(listDeleteRequests.mock.calls[0][0]).toEqual({ status: "pending" });
    expect(screen.getByRole("button", { name: "Pending" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Approve Deletion" })).toBeInTheDocument();
  });

  it("offers Pending and Decided, and no tab that mixes the two", () => {
    listDeleteRequests.mockResolvedValue({ data: { results: [] } });

    renderScreen(<DeleteRequestsPage />);

    expect(screen.getByRole("button", { name: "Pending" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Decided" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "All" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approved" })).not.toBeInTheDocument();
  });

  it("shows decided requests with their outcome and reason, and no action", async () => {
    listDeleteRequests.mockImplementation((params: { status?: string }) =>
      Promise.resolve({
        data: { results: params.status === "decided" ? [turnedDown, removed] : [waiting] },
      }),
    );

    renderScreen(<DeleteRequestsPage />);
    await screen.findByRole("link", { name: "Still waiting" });

    await userEvent.click(screen.getByRole("button", { name: "Decided" }));

    expect(await screen.findByRole("link", { name: "Turned down" })).toBeInTheDocument();
    expect(listDeleteRequests.mock.calls.at(-1)?.[0]).toEqual({ status: "decided" });
    expect(screen.getByText("Declined")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Kept for the archive")).toBeInTheDocument();
    expect(screen.getByText("Duplicate upload")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Approve Deletion/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Still waiting" })).not.toBeInTheDocument();
  });

  it("never offers an action on a declined row, even if one reaches the Pending list", async () => {
    // The WF-02 case: the server once answered `?status=pending` with everything.
    listDeleteRequests.mockResolvedValue({ data: { results: [waiting, turnedDown] } });

    renderScreen(<DeleteRequestsPage />);
    await screen.findByRole("link", { name: "Turned down" });

    expect(screen.getAllByRole("button", { name: "Approve Deletion" })).toHaveLength(1);
  });

  it("says plainly when nothing is decided yet", async () => {
    listDeleteRequests.mockResolvedValue({ data: { results: [] } });

    renderScreen(<DeleteRequestsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Decided" }));

    expect(await screen.findByText("No requests have been decided yet.")).toBeInTheDocument();
  });
});

describe("DeleteRequestsPage paging (IR-1076)", () => {
  const first = request({ id: 1, record_title: "First page paper", status: "declined", reviewed_at: "2026-11-02T08:00:00Z" });
  const second = request({ id: 2, record_title: "Second page paper", status: "approved", reviewed_at: "2026-11-01T08:00:00Z" });

  /** A server that has more than one page of decided requests. */
  function twoPages() {
    listDeleteRequests.mockImplementation((params: { status?: string; page?: number }) =>
      Promise.resolve({
        data: params.page === 2
          ? { results: [second], next: null }
          : { results: [first], next: "http://api/records/delete-requests/?page=2" },
      }),
    );
  }

  it("labels the requester's words as theirs, not as RDCO's decision", async () => {
    listDeleteRequests.mockResolvedValue({ data: { results: [request({})], next: null } });

    renderScreen(<DeleteRequestsPage />);

    expect(await screen.findByRole("columnheader", { name: "Requested because" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Reason" })).not.toBeInTheDocument();
  });

  it("offers Load more only when the server has another page, and appends it", async () => {
    twoPages();

    renderScreen(<DeleteRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("link", { name: "Second page paper" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "First page paper" })).toBeInTheDocument();
    expect(listDeleteRequests.mock.calls.at(-1)?.[0]).toEqual({ status: "pending", page: 2 });
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("shows no Load more when everything fits on one page", async () => {
    listDeleteRequests.mockResolvedValue({ data: { results: [first], next: null } });

    renderScreen(<DeleteRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });

    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("starts again from the first page when the tab changes", async () => {
    twoPages();

    renderScreen(<DeleteRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByRole("link", { name: "Second page paper" });

    await userEvent.click(screen.getByRole("button", { name: "Decided" }));

    await waitFor(() => expect(listDeleteRequests.mock.calls.at(-1)?.[0]).toEqual({ status: "decided" }));
    expect(await screen.findByRole("button", { name: "Load more" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Second page paper" })).not.toBeInTheDocument();
  });

  it("says so when the next page cannot be read, and keeps what is shown", async () => {
    listDeleteRequests.mockImplementation((params: { page?: number }) =>
      params.page === 2
        ? Promise.reject(new Error("boom"))
        : Promise.resolve({ data: { results: [first], next: "http://api/?page=2" } }),
    );

    renderScreen(<DeleteRequestsPage />);
    await screen.findByRole("link", { name: "First page paper" });

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load more/i);
    expect(screen.getByRole("link", { name: "First page paper" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load more" })).toBeInTheDocument();
  });
});

