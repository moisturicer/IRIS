import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { apiClient } from "@/api/client";
import { ROLES, type RoleName } from "@/lib/constants";
import type { ReviewAccess } from "@/types/auth";
import { useAuthStore } from "@/store/auth.store";
import { makeUser, validToken } from "@/test/authFixtures";
import { routes, router as browserRouter } from "./index";

vi.mock("@/api/client", () => ({ apiClient: { get: vi.fn() } }));

beforeEach(() => {
  browserRouter.dispose();
  vi.mocked(apiClient.get).mockResolvedValue({ data: { count: 0, results: [] } });
});
afterEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ user: null, accessToken: null, isAuthenticated: false });
});

const REVIEWS: ReviewAccess = { my_reviews: true, offices: ["itso"], is_coordinator: true };

function visit(path: string, role: RoleName, staff = false, review_access?: ReviewAccess) {
  useAuthStore.setState({
    user: makeUser({ role_name: role, is_staff: staff, is_superuser: staff, review_access }),
    accessToken: validToken(), authReady: true, isAuthenticated: true,
  });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

describe("role-owned addresses (IR-783)", () => {
  it.each([
    ["/rdco/users", "Users"],
    ["/rdco/role-requests", "Role Requests"],
    ["/rdco/download-requests", "Download Requests"],
    ["/rdco/delete-requests", "Delete Requests"],
  ])("opens %s for RDCO", async (path, title) => {
    visit(path, ROLES.RDCO);
    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  });

  it.each([
    ["/admin/users", "Users"],
    ["/admin/audit", "Audit Log"],
  ])("opens %s for the System Admin", async (path, title) => {
    visit(path, ROLES.SYSTEM_ADMIN);
    expect(await screen.findByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  });

  it.each(["/admin/role-requests", "/admin/download-requests", "/admin/delete-requests"])("removes %s without redirecting", async (path) => {
    const router = visit(path, ROLES.RDCO);
    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(path);
  });

  it.each([
    [ROLES.RDCO, "/admin/users", false],
    [ROLES.RDCO, "/admin/audit", false],
    [ROLES.RDCO, "/admin/audit", true],
    [ROLES.SYSTEM_ADMIN, "/rdco/users", false],
    [ROLES.SYSTEM_ADMIN, "/rdco/role-requests", false],
    [ROLES.SYSTEM_ADMIN, "/rdco/download-requests", false],
    [ROLES.SYSTEM_ADMIN, "/rdco/delete-requests", false],
    [ROLES.SYSTEM_ADMIN, "/review", false],
    [ROLES.SYSTEM_ADMIN, "/review/analytics", false],
    [ROLES.SYSTEM_ADMIN, "/review", true],
    [ROLES.SYSTEM_ADMIN, "/rdco/users", true],
  ])("refuses %s on %s (Django staff: %s)", async (role, path, staff) => {
    visit(path, role, staff);
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });
});

// IR-1085: the console is gated by its own entry in the access map, the one the
// sidebar lists it from, so an Adviser who types the address is refused.
describe("the office console address (IR-1085)", () => {
  it.each([ROLES.ADVISER, ROLES.STUDENT, ROLES.SYSTEM_ADMIN])("refuses %s", async (role) => {
    visit("/review/office", role, false, REVIEWS);
    expect(await screen.findByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });

  it.each([ROLES.ITSO, ROLES.RDCO])("opens for %s, and the sidebar links to it", async (role) => {
    const router = visit("/review/office", role, false, REVIEWS);
    expect(await screen.findByRole("link", { name: "Office console" })).toHaveAttribute("href", "/review/office");
    expect(screen.queryByRole("heading", { name: "Access denied" })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/review/office");
  });

  it("still sends an office member with no review work to Discover", async () => {
    const router = visit("/review/office", ROLES.ITSO, false, { ...REVIEWS, my_reviews: false });
    await screen.findByRole("navigation", { name: "Main" });
    await vi.waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});
