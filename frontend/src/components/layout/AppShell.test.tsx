/**
 * The app shell has no top bar (IR-519, IR-523).
 *
 * The fixed 58px header cost vertical space on every screen and carried a
 * search box with no handler. It is gone: on a desktop the bell sits at the
 * top of the sidebar; below `md`, where the sidebar is a drawer, a slim bar
 * that scrolls with the page holds only the menu button and the bell.
 * Reverses spec §4.2's "one app header on every screen" (amended here).
 *
 * The shell also picks each page's width from its route (IR-521): standard
 * unless the route's handle asks for "full".
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { makeUser } from "@/test/authFixtures";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";

import { AppShell } from "./AppShell";
import { PAGE_WIDTH } from "./PageContainer";

vi.mock("@/api/client", () => ({ apiClient: { get: vi.fn() } }));
vi.mock("@/api/notifications", () => ({ notificationsApi: { list: vi.fn() } }));

const { apiClient } = await import("@/api/client");
const { notificationsApi } = await import("@/api/notifications");

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        element: <AppShell />,
        children: [
          { path: "/records/mine", element: <h1>My Library</h1>, handle: { crumb: "My Library" } },
          { path: "/admin/audit", element: <h1>Audit Log</h1>, handle: { crumb: "Audit Log", width: "full" } },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  // The sidebar's badges and the bell's unread list, both empty.
  vi.mocked(apiClient.get).mockResolvedValue({ data: { pending_mine: 0, count: 0, results: [] } } as never);
  vi.mocked(notificationsApi.list).mockResolvedValue({ data: { results: [] } } as never);
  useAuthStore.setState({
    user: makeUser({ role_name: ROLES.STUDENT }),
    isAuthenticated: true,
  });
});

afterEach(() => vi.clearAllMocks());

describe("the app shell", () => {
  it("draws no top bar and no search box", async () => {
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  });

  it("keeps the bell in the sidebar, and a menu button and bell for phones", async () => {
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const sidebar = screen.getByRole("complementary", { name: "Sidebar" });
    expect(within(sidebar).getByRole("button", { name: /^Notifications/ })).toBeInTheDocument();

    const phoneBar = screen.getByRole("navigation", { name: "Menu" });
    expect(within(phoneBar).getByRole("button", { name: "Open menu" })).toBeInTheDocument();
    expect(within(phoneBar).getByRole("button", { name: /^Notifications/ })).toBeInTheDocument();
  });

  it("no longer lists Notifications among the sidebar's links", async () => {
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: /Notifications/ })).not.toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /Settings/ })).toBeInTheDocument();
  });

  it("gives a page the standard width unless its route asks for full", async () => {
    renderAt("/records/mine");

    const page = await screen.findByRole("heading", { name: "My Library" });
    expect(page.parentElement!.className).toContain(PAGE_WIDTH.standard);
  });

  it("gives a full-width route the whole width", async () => {
    renderAt("/admin/audit");

    const page = await screen.findByRole("heading", { name: "Audit Log" });
    expect(page.parentElement!.className).not.toContain(PAGE_WIDTH.standard);
  });
});
