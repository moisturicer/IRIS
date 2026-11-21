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
 * A page starts with its own title, with no breadcrumb above it (IR-1255).
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { makeUser } from "@/test/authFixtures";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";

import { AppShell } from "./AppShell";
import { NotificationBell } from "./NotificationBell";
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
          { path: "/records/mine", element: <h1>My Library</h1>, handle: { title: "My Library" } },
          { path: "/admin/audit", element: <h1>Audit Log</h1>, handle: { title: "Audit Log", width: "full" } },
          // Stands in for Ask IRIS, whose toolbar mounts a third bell.
          {
            path: "/with-bell",
            element: (
              <>
                <h1>Page with a bell</h1>
                <NotificationBell />
              </>
            ),
          },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  return { router, ...render(<RouterProvider router={router} />) };
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
  it("starts a page with its own title, under no breadcrumb (IR-1255)", async () => {
    renderAt("/records/mine");

    expect(await screen.findByRole("heading", { level: 1, name: "My Library" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Breadcrumb" })).not.toBeInTheDocument();
    // Discover is still a click away, from the sidebar, and only from there.
    const discover = screen.getByRole("link", { name: "Discover" });
    expect(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Discover" })).toBe(discover);
  });

  // The shell owns Publish (IR-1258), so `?publish=` opens it over the page
  // the reader is on. A reader who cannot author gets its short explanation,
  // which reads nothing from the server -- enough to see where it opens.
  it("opens Publish over the page it is on and leaves the reader there (IR-1258)", async () => {
    useAuthStore.setState({ user: makeUser({ role_name: ROLES.STUDENT, can_author: false }) });
    const user = userEvent.setup();
    const { router } = renderAt("/records/mine?section=saved&publish=12");

    const dialog = await screen.findByRole("dialog", { name: "Publishing isn't available to your account" });
    expect(screen.getByRole("heading", { level: 1, name: "My Library" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "My Library" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Discover" })).not.toHaveAttribute("aria-current");

    await user.click(within(dialog).getByRole("button", { name: "Got it" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/records/mine");
    expect(router.state.location.search).toBe("?section=saved");
  });

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

  it("puts the IRIS mark in the phone bar, linking to Discover (audit RES-04)", async () => {
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const phoneBar = screen.getByRole("navigation", { name: "Menu" });
    expect(within(phoneBar).getByRole("link", { name: "IRIS, go to Discover" })).toHaveAttribute("href", "/");
  });

  it("lists neither Notifications nor Settings among the sidebar's links", async () => {
    // The bell is the notification entry (IR-519); Settings is in the account
    // menu (IR-413).
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: /Notifications/ })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: /Settings/ })).not.toBeInTheDocument();
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

  it("fetches unread notifications once however many bells are mounted (IR-370)", async () => {
    renderAt("/with-bell");

    await screen.findByRole("heading", { name: "Page with a bell" });
    // The sidebar's bell, the phone bar's and the page's own.
    expect(screen.getAllByRole("button", { name: /^Notifications/ })).toHaveLength(3);
    expect(notificationsApi.list).toHaveBeenCalledTimes(1);
    expect(notificationsApi.list).toHaveBeenCalledWith(true);
  });

  describe("skip link (IR-1184, WCAG 2.4.1)", () => {
    it("is the first tab stop, and Enter moves focus into main", async () => {
      const user = userEvent.setup();
      renderAt("/records/mine");
      await screen.findByRole("heading", { name: "My Library" });

      await user.tab();
      const skip = screen.getByRole("link", { name: "Skip to content" });
      expect(skip).toHaveFocus();

      await user.keyboard("{Enter}");
      expect(screen.getByRole("main")).toHaveFocus();
    });

    it("comes before the sidebar, so Enter spares the reader its stops", async () => {
      const user = userEvent.setup();
      renderAt("/records/mine");
      await screen.findByRole("heading", { name: "My Library" });
      const sidebar = screen.getByRole("complementary", { name: "Sidebar" });

      // Without Enter, the second stop is the sidebar's first...
      await user.tab();
      await user.tab();
      expect(sidebar).toContainElement(document.activeElement as HTMLElement);

      // ...and with it, focus is already in main, past all of them.
      (document.activeElement as HTMLElement).blur();
      await user.tab();
      await user.keyboard("{Enter}");
      expect(sidebar).not.toContainElement(document.activeElement as HTMLElement);
      expect(screen.getByRole("main")).toHaveFocus();
    });

    it("still works after a route change", async () => {
      const user = userEvent.setup();
      const { router } = renderAt("/records/mine");
      await screen.findByRole("heading", { name: "My Library" });

      await act(() => router.navigate("/admin/audit"));
      await screen.findByRole("heading", { name: "Audit Log" });
      // A new page load, or the back button, leaves focus at the document.
      (document.activeElement as HTMLElement | null)?.blur();

      await user.tab();
      expect(screen.getByRole("link", { name: "Skip to content" })).toHaveFocus();
      await user.keyboard("{Enter}");
      expect(screen.getByRole("main")).toHaveFocus();
    });
  });

  it("never makes main a scroll container, so sticky chrome keeps working (IR-351, IR-534)", async () => {
    // Spec Appendix K: F1 must not add `overflow` to `main`. The window is the
    // scroll root; any overflow value on `main` makes it the nearest scroll
    // container and leaves every `sticky` descendant inert.
    for (const path of ["/records/mine", "/admin/audit"]) {
      const { unmount } = renderAt(path);
      await screen.findByRole("heading", { level: 1 });
      const main = screen.getByRole("main");
      expect(main.className).not.toMatch(/(^|\s|:)overflow-/);
      expect(main.style.overflow).toBe("");
      unmount();
    }
  });
});
