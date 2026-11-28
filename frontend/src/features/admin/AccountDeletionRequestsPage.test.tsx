/**
 * IR-788: the System Admin's Account Deletion Requests page. Who asked and
 * when, what blocks each request in plain words, Confirm disabled while
 * anything blocks it, Reject with a required reason, Confirm asking first,
 * and a stale decision showing the server's refusal. Controls come from the
 * request's capabilities; the page compares no role names.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AccountDeletionRequest } from "@/api/accounts";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { emitLiveHint } from "@/lib/live";
import { act, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import AccountDeletionRequestsPage from "./AccountDeletionRequestsPage";

const deletionRequests = vi.fn();
const confirmDeletion = vi.fn();
const rejectDeletion = vi.fn();

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    deletionRequests: (...args: unknown[]) => deletionRequests(...args),
    confirmDeletion: (...args: unknown[]) => confirmDeletion(...args),
    rejectDeletion: (...args: unknown[]) => rejectDeletion(...args),
  },
}));

function request(overrides: Partial<AccountDeletionRequest> = {}): AccountDeletionRequest {
  return {
    id: 4,
    status: "pending",
    created_at: "2026-11-05T08:00:00Z",
    decided_at: null,
    reason: "",
    user: { id: 9, name: "Ana Reyes", email: "ana@cit.edu", role: "Student" },
    blockers: [],
    capabilities: { can_confirm: true, can_reject: true },
    ...overrides,
  };
}

const BLOCKED = request({
  blockers: [{
    kind: "sole_owner_in_review", record: 7, title: "Rice yields",
    message: "“Rice yields” is in review and has no other owner. RDCO must withdraw it or add an owner.",
  }],
  capabilities: { can_confirm: false, can_reject: true },
});

beforeEach(() => {
  deletionRequests.mockReset();
  confirmDeletion.mockReset();
  rejectDeletion.mockReset();
});

describe("AccountDeletionRequestsPage paging (IR-1100)", () => {
  const first = request({ id: 1, user: { id: 1, name: "First Page Person", email: "one@cit.edu", role: "Student" } });
  const second = request({ id: 2, user: { id: 2, name: "Second Page Person", email: "two@cit.edu", role: "Student" } });

  /** A server with more than one page of requests. */
  function twoPages() {
    deletionRequests.mockImplementation((opts?: { page?: number }) =>
      Promise.resolve({
        data: opts?.page === 2
          ? { results: [second], next: null }
          : { results: [first], next: "http://api/users/deletion-requests/?page=2" },
      }),
    );
  }

  it("offers Load more when the server has another page, and appends it", async () => {
    twoPages();
    renderScreen(<AccountDeletionRequestsPage />);
    await screen.findByRole("listitem", { name: "First Page Person" });

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("listitem", { name: "Second Page Person" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "First Page Person" })).toBeInTheDocument();
    expect(deletionRequests.mock.calls.at(-1)?.[0]).toMatchObject({ page: 2 });
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("shows no Load more when everything fits on one page", async () => {
    deletionRequests.mockResolvedValue({ data: { results: [first], next: null } });
    renderScreen(<AccountDeletionRequestsPage />);
    await screen.findByRole("listitem", { name: "First Page Person" });

    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("starts again from the first page after a decision refreshes the list", async () => {
    deletionRequests.mockImplementation((opts?: { page?: number }) =>
      Promise.resolve({
        data: opts?.page === 2
          ? { results: [second], next: null }
          : { results: [first], next: "http://api/users/deletion-requests/?page=2" },
      }),
    );
    confirmDeletion.mockResolvedValue({ data: first });
    renderScreen(<AccountDeletionRequestsPage />);
    await screen.findByRole("listitem", { name: "First Page Person" });
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByRole("listitem", { name: "Second Page Person" });

    await userEvent.click(within(screen.getByRole("listitem", { name: "First Page Person" }))
      .getByRole("button", { name: "Confirm deletion" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));

    expect(await screen.findByRole("status")).toHaveTextContent("First Page Person's account was deleted.");
    await waitFor(() => expect(screen.queryByRole("listitem", { name: "Second Page Person" })).not.toBeInTheDocument());
    expect(await screen.findByRole("button", { name: "Load more" })).toBeInTheDocument();
  });

  it("says so when the next page cannot be read, and keeps what is shown", async () => {
    deletionRequests.mockImplementation((opts?: { page?: number }) =>
      opts?.page === 2
        ? Promise.reject(new Error("boom"))
        : Promise.resolve({ data: { results: [first], next: "http://api/?page=2" } }),
    );
    renderScreen(<AccountDeletionRequestsPage />);
    await screen.findByRole("listitem", { name: "First Page Person" });

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load more/i);
    expect(screen.getByRole("listitem", { name: "First Page Person" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Load more" })).toBeInTheDocument();
  });
});

describe("AccountDeletionRequestsPage", () => {
  it("lists who asked and when, with nothing blocking, and passes axe", async () => {
    deletionRequests.mockResolvedValue({ data: { results: [request()] } });
    const { container } = renderScreen(<AccountDeletionRequestsPage />);

    const item = await screen.findByRole("listitem", { name: "Ana Reyes" });
    expect(within(item).getByText(/ana@cit\.edu/)).toBeInTheDocument();
    expect(within(item).getByText(/^Asked /)).toBeInTheDocument();
    expect(within(item).getByText("Nothing is blocking it.")).toBeInTheDocument();
    expect(within(item).getByRole("button", { name: "Confirm deletion" })).toBeEnabled();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows what blocks a request and disables Confirm, saying who must clear it", async () => {
    deletionRequests.mockResolvedValue({ data: { results: [BLOCKED] } });
    renderScreen(<AccountDeletionRequestsPage />);

    const item = await screen.findByRole("listitem", { name: "Ana Reyes" });
    expect(within(item).getByText(/RDCO must withdraw it or add an owner/)).toBeInTheDocument();
    const confirm = within(item).getByRole("button", { name: "Confirm deletion" });
    expect(confirm).toBeDisabled();
    expect(confirm).toHaveAccessibleDescription(/RDCO or the person clears/);
    expect(within(item).getByRole("button", { name: "Reject" })).toBeEnabled();
  });

  it("offers no decision on a request the capabilities withhold, such as one's own", async () => {
    deletionRequests.mockResolvedValue({
      data: { results: [request({ capabilities: { can_confirm: false, can_reject: false } })] },
    });
    renderScreen(<AccountDeletionRequestsPage />);

    const item = await screen.findByRole("listitem", { name: "Ana Reyes" });
    expect(within(item).getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(within(item).getByRole("button", { name: "Confirm deletion" }))
      .toHaveAccessibleDescription(/Another System Admin must/);
  });

  it("asks before confirming, says it can't be undone, then confirms", async () => {
    deletionRequests
      .mockResolvedValueOnce({ data: { results: [request()] } })
      .mockResolvedValueOnce({ data: { results: [] } });
    confirmDeletion.mockResolvedValue({ data: request({ status: "approved" }) });
    const { container } = renderScreen(<AccountDeletionRequestsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Confirm deletion" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this account?" });
    expect(dialog).toHaveTextContent(/can't be undone/);
    expect(confirmDeletion).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(within(dialog).getByRole("button", { name: "Delete account" }));
    expect(confirmDeletion).toHaveBeenCalledWith(4);
    expect(await screen.findByRole("status")).toHaveTextContent("Ana Reyes's account was deleted.");
    expect(await screen.findByText("No deletion requests")).toBeInTheDocument();
  });

  it("shows the server's refusal when the decision is stale", async () => {
    deletionRequests.mockResolvedValue({ data: { results: [request()] } });
    confirmDeletion.mockRejectedValue({
      response: { status: 409, data: { detail: "This request was already decided or cancelled. Reload to see where it stands." } },
    });
    renderScreen(<AccountDeletionRequestsPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Confirm deletion" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));

    const dialog = screen.getByRole("dialog", { name: "Delete this account?" });
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/already decided or cancelled/);
    await waitFor(() => expect(deletionRequests).toHaveBeenCalledTimes(2));
  });

  it("needs a reason to reject, and sends it", async () => {
    deletionRequests
      .mockResolvedValueOnce({ data: { results: [BLOCKED] } })
      .mockResolvedValueOnce({ data: { results: [] } });
    rejectDeletion.mockResolvedValue({ data: request({ status: "declined" }) });
    const { container } = renderScreen(<AccountDeletionRequestsPage />);

    await userEvent.click(within(await screen.findByRole("listitem", { name: "Ana Reyes" }))
      .getByRole("button", { name: "Reject" }));
    const dialog = screen.getByRole("dialog", { name: "Reject account deletion" });
    const submit = within(dialog).getByRole("button", { name: "Reject request" });
    expect(submit).toBeDisabled();
    await expectNoBlockingA11yViolations(container);

    await userEvent.type(within(dialog).getByRole("textbox", { name: "Reason" }), "Thesis still under examination.");
    await userEvent.click(submit);

    expect(rejectDeletion).toHaveBeenCalledWith(4, "Thesis still under examination.");
    expect(await screen.findByRole("status")).toHaveTextContent(/rejected. They have been told why/);
  });
});

describe("AccountDeletionRequestsPage, live (ADR-073, IR-1350)", () => {
  const ana = request();
  const ben = request({ id: 5, user: { id: 10, name: "Ben Lim", email: "ben@cit.edu", role: "Student" } });

  it("shows a request made elsewhere once a queues hint arrives", async () => {
    deletionRequests.mockResolvedValue({ data: { results: [ana], next: null } });
    renderScreen(<AccountDeletionRequestsPage />);
    await screen.findByRole("listitem", { name: "Ana Reyes" });

    deletionRequests.mockResolvedValue({ data: { results: [ana, ben], next: null } });
    act(() => { emitLiveHint(["queues"]); });

    expect(await screen.findByRole("listitem", { name: "Ben Lim" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Ana Reyes" })).toBeInTheDocument();
  });

  it("keeps the list when the live read fails", async () => {
    deletionRequests.mockResolvedValue({ data: { results: [ana], next: null } });
    renderScreen(<AccountDeletionRequestsPage />);
    await screen.findByRole("listitem", { name: "Ana Reyes" });

    deletionRequests.mockRejectedValue(new Error("offline"));
    act(() => { emitLiveHint(["queues"]); });

    await waitFor(() => expect(deletionRequests).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("listitem", { name: "Ana Reyes" })).toBeInTheDocument();
  });
});
