/**
 * Role Requests when its list fails to load (IR-745): "No role requests" would
 * tell RDCO there is nothing to decide when there may be.
 *
 * IR-1100: the API pages at 20, so a queue longer than one page offers Load more.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

import RoleRequestsPage from "./RoleRequestsPage";

const roleRequests = vi.fn();

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    roleRequests: (...args: unknown[]) => roleRequests(...args),
    decideRequest: vi.fn(),
  },
}));

afterEach(() => vi.clearAllMocks());

describe("Role Requests", () => {
  it("says a failed load failed, never that everything is decided, and tries again", async () => {
    roleRequests
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValueOnce({ data: { count: 0, results: [] } });
    renderScreen(<RoleRequestsPage />);

    expect(await screen.findByRole("heading", { name: "Couldn't load role requests" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "No role requests" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "No role requests" })).toBeInTheDocument();
  });
});

describe("Role Requests paging (IR-1100)", () => {
  function row(id: number, name: string) {
    return {
      id, user_name: name, role_name: "Adviser", status: "pending", created_at: "2026-11-01T08:00:00Z",
    };
  }

  it("offers Load more when the server has another page, and appends it", async () => {
    roleRequests.mockImplementation((opts?: { page?: number }) =>
      Promise.resolve({
        data: opts?.page === 2
          ? { count: 2, next: null, results: [row(2, "Second Page Person")] }
          : { count: 2, next: "http://api/users/role-requests/?page=2", results: [row(1, "First Page Person")] },
      }),
    );
    renderScreen(<RoleRequestsPage />);
    await screen.findByText("First Page Person");

    await userEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByText("Second Page Person")).toBeInTheDocument();
    expect(screen.getByText("First Page Person")).toBeInTheDocument();
    expect(roleRequests.mock.calls.at(-1)?.[0]).toMatchObject({ page: 2 });
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("shows no Load more when everything fits on one page", async () => {
    roleRequests.mockResolvedValue({ data: { count: 1, next: null, results: [row(1, "First Page Person")] } });
    renderScreen(<RoleRequestsPage />);
    await screen.findByText("First Page Person");

    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });
});
