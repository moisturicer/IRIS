import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { apiClient } from "@/api/client";
import { ROLES, type RoleName } from "@/lib/constants";
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

function visit(path: string, role: RoleName, staff = false) {
  useAuthStore.setState({
    user: makeUser({ role_name: role, is_staff: staff, is_superuser: staff }),
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
