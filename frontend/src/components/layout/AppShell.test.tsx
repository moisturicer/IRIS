/**
 * The app shell has no top bar (IR-519, IR-523).
 *
 * The fixed 58px header cost vertical space on every screen and carried a
 * search box with no handler. It is gone: on a desktop Notifications is a
 * link in the sidebar; below `md`, where the sidebar is a drawer, a slim bar
 * that scrolls with the page holds only the menu button and the bell.
 * Reverses spec §4.2's "one app header on every screen" (amended here).
 *
 * The shell draws one frame around every page, for every role (IR-521,
 * IR-1353): the same gutter and the same 1440px cap, including the admin
 * tables that used to run edge to edge and Discover, which drew its own. Ask
 * IRIS and a record lay out their own page and get none.
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
import { ROLES, type RoleName } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";

import { AppShell } from "./AppShell";
import { NotificationBell } from "./NotificationBell";
import { PAGE_GUTTER, PAGE_WIDTH } from "./PageContainer";

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
          { path: "/", element: <h1>Discover</h1>, handle: { title: "Discover" } },
          { path: "/records/mine", element: <h1>My Library</h1>, handle: { title: "My Library" } },
          { path: "/rdco/role-requests", element: <h1>Role requests</h1>, handle: { title: "Role requests" } },
          { path: "/admin/audit", element: <h1>Audit Log</h1>, handle: { title: "Audit Log" } },
          { path: "/ai", element: <h1>Ask IRIS</h1>, handle: { title: "Ask IRIS" } },
          { path: "/records/:id", element: <h1>A paper</h1>, handle: { title: "Paper" } },
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

  it("lists Notifications in the sidebar, and keeps a menu button and bell for phones", async () => {
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const sidebar = screen.getByRole("complementary", { name: "Sidebar" });
    // A link, not a bell: the sidebar's header holds no bell any more.
    expect(within(sidebar).getByRole("link", { name: /^Notifications/ })).toHaveAttribute("href", "/notifications");
    expect(within(sidebar).queryByRole("button", { name: /^Notifications/ })).not.toBeInTheDocument();

    const phoneBar = screen.getByRole("navigation", { name: "Menu" });
    expect(within(phoneBar).getByRole("button", { name: "Open menu" })).toBeInTheDocument();
    expect(within(phoneBar).getByRole("button", { name: /^Notifications/ })).toBeInTheDocument();
  });

  it("gives the sidebar's Notifications link the same unread count as the bell", async () => {
    vi.mocked(notificationsApi.list).mockResolvedValue({ data: { count: 3, results: [] } } as never);
    renderAt("/records/mine");

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(await within(nav).findByRole("link", { name: "Notifications, 3 unread" })).toBeInTheDocument();
    const phoneBar = screen.getByRole("navigation", { name: "Menu" });
    expect(within(phoneBar).getByRole("button", { name: "Notifications, 3 unread" })).toBeInTheDocument();
  });

  it("puts the IRIS mark in the phone bar, linking to Discover (audit RES-04)", async () => {
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const phoneBar = screen.getByRole("navigation", { name: "Menu" });
    expect(within(phoneBar).getByRole("link", { name: "IRIS, go to Discover" })).toHaveAttribute("href", "/");
  });

  it("does not list Settings among the sidebar's links", async () => {
    // Settings is in the account menu (IR-413).
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: /Settings/ })).not.toBeInTheDocument();
  });

  describe("one page frame for every role (IR-1353)", () => {
    // A sample of each role's pages: an ordinary page, Discover, and the admin
    // tables that used to run edge to edge.
    const framed: [RoleName, string, string][] = [
      [ROLES.STUDENT, "/", "Discover"],
      [ROLES.STUDENT, "/records/mine", "My Library"],
      [ROLES.ADVISER, "/records/mine", "My Library"],
      [ROLES.ITSO, "/", "Discover"],
      [ROLES.RDCO, "/rdco/role-requests", "Role requests"],
      [ROLES.SYSTEM_ADMIN, "/admin/audit", "Audit Log"],
    ];

    it.each(framed)("frames a %s's %s page with the gutter outside the cap", async (role, path, title) => {
      useAuthStore.setState({ user: makeUser({ role_name: role }) });
      renderAt(path);

      const heading = await screen.findByRole("heading", { name: title });
      const main = screen.getByRole("main");
      const cap = heading.parentElement!;
      expect(cap.className).toContain(PAGE_WIDTH.standard);
      expect(cap.parentElement!.className).toBe(PAGE_GUTTER);
      expect(cap.parentElement!.parentElement).toBe(main);
      // main itself adds nothing, so the gutter is the whole margin.
      expect(main.className).not.toMatch(/(^|\s|:)p[xytblr]?-\d/);
    });

    it.each([["/ai", "Ask IRIS"], ["/records/12", "A paper"]])(
      "draws no frame around %s, which lays out its own page", async (path, title) => {
        renderAt(path);

        const heading = await screen.findByRole("heading", { name: title });
        expect(heading.parentElement).toBe(screen.getByRole("main"));
      },
    );
  });

  it("fetches unread notifications once however many bells are mounted (IR-370)", async () => {
    renderAt("/with-bell");

    await screen.findByRole("heading", { name: "Page with a bell" });
    // The phone bar's bell and the page's own, plus the sidebar's count.
    expect(screen.getAllByRole("button", { name: /^Notifications/ })).toHaveLength(2);
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
