/**
 * Role Requests when its list fails to load (IR-745): "All caught up!" would
 * tell RDCO there is nothing to decide when there may be.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";

import RoleRequestsPage from "./RoleRequestsPage";

const roleRequests = vi.fn();

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    roleRequests: () => roleRequests(),
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
    expect(screen.queryByText("All caught up!")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("All caught up!")).toBeInTheDocument();
  });
});
