/**
 * IR-914: RDCO's delete-request queue reads under `useApiRead`. A timed-out
 * read is the "interrupted" state with a Retry, a change of filter cancels the
 * read in flight, and the reader's Retry is the only thing that repeats it.
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

    await userEvent.click(screen.getByRole("button", { name: "Approved" }));

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
