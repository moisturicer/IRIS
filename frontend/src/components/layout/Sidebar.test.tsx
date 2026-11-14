/**
 * The sidebar (IR-413, spec §4.1-§4.2).
 *
 * One short list, My Reviews only for a user with review work, RDCO's
 * Administration group, and an account menu holding Profile, Settings, Help
 * and Sign out. Below `md` it is a drawer that is out of the tab order while
 * closed, takes focus when opened, and closes on Escape.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";

import { makeUser } from "@/test/authFixtures";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { ROLES, type RoleName } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore } from "@/store/ui.store";
import { ReviewAccessRoute } from "@/components/auth/ReviewAccessRoute";

import { AppShell } from "./AppShell";

vi.mock("@/api/client", () => ({ apiClient: { get: vi.fn() } }));
vi.mock("@/api/notifications", () => ({ notificationsApi: { list: vi.fn() } }));
vi.mock("@/api/auth", () => ({ authApi: { logout: vi.fn() } }));

const { apiClient } = await import("@/api/client");
const { notificationsApi } = await import("@/api/notifications");
const { authApi } = await import("@/api/auth");

function signIn(role: RoleName, myReviews?: boolean) {
  useAuthStore.setState({
    user: makeUser({
      role_name: role,
      first_name: "Ana",
      last_name: "Adviser",
      email: "adviser@cit.edu",
      review_access: myReviews == null
        ? undefined
        : { my_reviews: myReviews, offices: [], is_coordinator: false },
    }),
    isAuthenticated: true,
  });
}

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        element: <AppShell />,
        children: [
          { path: "/", element: <h1>Discover</h1> },
          { path: "/records/mine", element: <h1>My Library</h1> },
          { path: "/profile", element: <h1>Profile</h1> },
          { path: "/settings", element: <h1>Settings</h1> },
          {
            element: <ReviewAccessRoute />,
            children: [{ path: "/review", element: <h1>My Reviews</h1> }],
          },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

/** Pretend the window is phone-width, where the sidebar is a drawer. */
function atPhoneWidth() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("max-width: 767"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

/**
 * Pretend the window is `px` wide: a media query matches when every
 * min-width / max-width it names holds (IR-1086).
 */
function atWidth(initial: number) {
  let px = initial;
  const watchers = new Set<{ query: string; notify: (matches: boolean) => void }>();
  const matchesAt = (query: string) => {
    const min = /min-width:\s*([\d.]+)px/.exec(query);
    const max = /max-width:\s*([\d.]+)px/.exec(query);
    return (!min || px >= Number(min[1])) && (!max || px <= Number(max[1]));
  };
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() { return matchesAt(query); },
    media: query,
    addEventListener: (_: string, notify: (event: { matches: boolean }) => void) =>
      watchers.add({ query, notify: (matches) => notify({ matches }) }),
    removeEventListener: () => {},
  }));
  /** Resize the window, telling every query that now matches or stops matching. */
  return (next: number) => {
    px = next;
    act(() => watchers.forEach((w) => w.notify(matchesAt(w.query))));
  };
}

const mainLinks = () =>
  within(screen.getByRole("navigation", { name: "Main" }))
    .getAllByRole("link")
    .map((link) => link.textContent?.trim());

beforeEach(() => {
  vi.mocked(apiClient.get).mockResolvedValue({ data: { count: 0, results: [] } } as never);
  vi.mocked(notificationsApi.list).mockResolvedValue({ data: { results: [] } } as never);
  vi.mocked(authApi.logout).mockResolvedValue({} as never);
  useUIStore.setState({ sidebarOpen: false, sidebarCollapsed: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("the sidebar's list", () => {
  it("is one short list with no section headings for a Student", async () => {
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    expect(mainLinks()).toEqual(["Discover", "Ask IRIS", "My Library", "Calls & Conferences"]);
    expect(screen.queryByText("Research Exploration")).not.toBeInTheDocument();
    expect(screen.queryByText("Tools")).not.toBeInTheDocument();
  });

  it("marks the page you are on", async () => {
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "My Library" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Discover" })).not.toHaveAttribute("aria-current");
  });

  it("shows My Reviews to an office member with review work", async () => {
    signIn(ROLES.ITSO, true);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    expect(mainLinks()).toContain("My Reviews");
  });

  it("hides My Reviews from an Adviser with no review work", async () => {
    signIn(ROLES.ADVISER, false);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    expect(mainLinks()).not.toContain("My Reviews");
  });

  it("names RDCO's group and counts its waiting role requests", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { count: 3, results: [] } } as never);
    signIn(ROLES.RDCO, true);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const admin = screen.getByRole("list", { name: "RDCO" });
    expect(within(admin).getAllByRole("link").map((l) => l.textContent?.trim())[0]).toBe("Import Records");
    expect(await within(admin).findByRole("link", { name: "Role Requests, 3 waiting" })).toHaveAttribute("href", "/rdco/role-requests");
    expect(within(admin).getByRole("link", { name: "Users" })).toHaveAttribute("href", "/rdco/users");
    expect(within(admin).getByRole("link", { name: "Download Requests" })).toHaveAttribute("href", "/rdco/download-requests");
    expect(within(admin).getByRole("link", { name: "Delete Requests" })).toHaveAttribute("href", "/rdco/delete-requests");
    expect(screen.queryByRole("link", { name: "Audit Log" })).not.toBeInTheDocument();
  });

  it.each([false, true])("gives the System Admin only its administration and catalogue links (collapsed: %s)", async (collapsed) => {
    useUIStore.setState({ sidebarCollapsed: collapsed });
    signIn(ROLES.SYSTEM_ADMIN, true);
    const { container } = renderAt("/");

    await screen.findByRole("heading", { name: "Discover" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link").map((link) => link.textContent?.trim())).toEqual(["Discover", "Users", "Audit Log", "Account Deletions", "Retention", "Notices"]);
    const admin = within(nav).getByRole("list", { name: "Administration" });
    expect(within(admin).getByRole("link", { name: "Users" })).toHaveAttribute("href", "/admin/users");
    expect(within(admin).getByRole("link", { name: "Audit Log" })).toHaveAttribute("href", "/admin/audit");
    // IR-788 adds the account deletion queue to the System Admin's section.
    expect(within(admin).getByRole("link", { name: "Account Deletions" }))
      .toHaveAttribute("href", "/admin/account-deletion-requests");
    // IR-795 adds the retention periods.
    expect(within(admin).getByRole("link", { name: "Retention" })).toHaveAttribute("href", "/admin/retention");
    // IR-800 adds the Notices page, read-only for the System Admin.
    expect(within(admin).getByRole("link", { name: "Notices" })).toHaveAttribute("href", "/notices");
    expect(within(nav).queryByRole("list", { name: "RDCO" })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("keeps every link named on the collapsed rail", async () => {
    useUIStore.setState({ sidebarCollapsed: true });
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    expect(mainLinks()).toEqual(["Discover", "Ask IRIS", "My Library", "Calls & Conferences"]);
    // jsdom applies no CSS, so the names above would be there whether the
    // labels were `md:sr-only` or `md:hidden`. The class is what keeps them
    // in the accessibility tree on the rail, so it is what is checked.
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const label of within(nav).getAllByText(/^(Discover|Ask IRIS|My Library|Calls & Conferences)$/)) {
      expect(label).toHaveClass("md:sr-only");
      expect(label).not.toHaveClass("md:hidden");
    }
    expect(screen.getByRole("button", { name: "Open sidebar" })).toBeInTheDocument();
  });

  it("collapses and expands from the logo without a footer control", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    await user.click(screen.getByRole("button", { name: "Open sidebar" }));
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    expect(screen.queryByText("Collapse")).not.toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations", async () => {
    signIn(ROLES.RDCO, true);
    const { container } = renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    await expectNoBlockingA11yViolations(container);
  });
});

/** `/dashboard/stats/` says this many of the user's records wait on them. */
function waitingOnYou(needsActionMine: number) {
  vi.mocked(apiClient.get).mockImplementation(((url: string) =>
    Promise.resolve({
      data: url === "/dashboard/stats/"
        ? { needs_action_mine: needsActionMine }
        : { count: 0, results: [] },
    })) as never);
}

describe("the My Library dot (IR-534, B2)", () => {
  it("appears when a record waits on you, and says so to a screen reader", async () => {
    waitingOnYou(2);
    signIn(ROLES.STUDENT);
    renderAt("/");

    await screen.findByRole("heading", { name: "Discover" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(
      await within(nav).findByRole("link", { name: "My Library, something needs your action" }),
    ).toBeInTheDocument();
  });

  it("is absent when nothing waits on you", async () => {
    waitingOnYou(0);
    signIn(ROLES.ADVISER, true);
    renderAt("/");

    await screen.findByRole("heading", { name: "Discover" });
    await vi.waitFor(() => expect(apiClient.get).toHaveBeenCalledWith("/dashboard/stats/"));
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "My Library" })).toBeInTheDocument();
  });

  it("stays named on the collapsed rail", async () => {
    useUIStore.setState({ sidebarCollapsed: true });
    waitingOnYou(1);
    signIn(ROLES.STUDENT);
    renderAt("/");

    await screen.findByRole("heading", { name: "Discover" });
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(
      await within(nav).findByRole("link", { name: "My Library, something needs your action" }),
    ).toBeInTheDocument();
  });
});

describe("the account menu", () => {
  // IR-933: Profile (who you are) and Settings (your account) are two pages.
  it("holds Profile, Settings, Help and Sign out", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const trigger = await screen.findByRole("button", { name: /Ana Adviser.*account menu/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Profile" })).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.queryByRole("link", { name: "Settings & Profile" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Help" })).toHaveAttribute("href", "/help");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("opens Profile and Settings, each closing the menu behind it", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await user.click(await screen.findByRole("button", { name: /account menu/ }));
    await user.click(screen.getByRole("link", { name: "Profile" }));
    expect(await screen.findByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Help" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /account menu/ }));
    await user.click(screen.getByRole("link", { name: "Settings" }));
    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Help" })).not.toBeInTheDocument();
  });

  it("closes on Escape and gives focus back to its button", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const trigger = await screen.findByRole("button", { name: /account menu/ });
    await user.click(trigger);
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  // IR-778, WCAG 2.5.3 Label in Name: a speech-input user says what the button
  // shows, so its name must begin with the visible name and role, in order.
  // The name is computed from that visible text, never set beside it in an
  // `aria-label`: axe's `label-content-name-mismatch` flagged the old label in
  // Chromium, but cannot see the mismatch under jsdom, which has no layout.
  it.each([
    ["expanded", false],
    ["collapsed", true],
  ])("is named by the name and role it shows (%s rail)", async (_, collapsed) => {
    useUIStore.setState({ sidebarCollapsed: collapsed });
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const trigger = await screen.findByRole("button", { name: /account menu/ });
    expect(trigger).toHaveAccessibleName("Ana Adviser, Student, account menu");
    expect(trigger).not.toHaveAttribute("aria-label");
  });

  it("signs out", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await user.click(await screen.findByRole("button", { name: /account menu/ }));
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(authApi.logout).toHaveBeenCalled();
    expect(useAuthStore.getState().user).toBeNull();
  });
});

describe("the phone drawer", () => {
  it("is out of the tab order while it is closed", async () => {
    atPhoneWidth();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    expect(screen.getByRole("complementary", { name: "Sidebar", hidden: true })).toHaveAttribute("inert");
  });

  it("takes focus when opened, leaves the page behind inert, and closes on Escape", async () => {
    const user = userEvent.setup();
    atPhoneWidth();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const page = await screen.findByRole("heading", { name: "My Library" });
    const openMenu = screen.getByRole("button", { name: "Open menu" });
    await user.click(openMenu);

    const sidebar = screen.getByRole("complementary", { name: "Sidebar" });
    expect(sidebar).not.toHaveAttribute("inert");
    expect(within(sidebar).getByRole("button", { name: "Close menu" })).toHaveFocus();
    expect(page.closest("[inert]")).not.toBeNull();

    await user.keyboard("{Escape}");
    expect(useUIStore.getState().sidebarOpen).toBe(false);
    expect(openMenu).toHaveFocus();
  });
});

describe("the phone drawer and its account menu", () => {
  it("closes only the account menu on Escape, not the drawer around it", async () => {
    const user = userEvent.setup();
    atPhoneWidth();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await user.click(await screen.findByRole("button", { name: "Open menu" }));
    const trigger = screen.getByRole("button", { name: /account menu/ });
    await user.click(trigger);
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(useUIStore.getState().sidebarOpen).toBe(true);
    expect(trigger).toHaveFocus();
  });

  it("closes after a link is chosen without pulling focus back to Open menu", async () => {
    const user = userEvent.setup();
    atPhoneWidth();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const openMenu = await screen.findByRole("button", { name: "Open menu" });
    await user.click(openMenu);
    await user.click(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Discover" }));

    expect(await screen.findByRole("heading", { name: "Discover" })).toBeInTheDocument();
    expect(useUIStore.getState().sidebarOpen).toBe(false);
    expect(openMenu).not.toHaveFocus();
  });
});

describe.each([768, 1023])("the tablet icon rail at %i px (IR-1086)", (width) => {
  const LABELS = /^(Discover|Ask IRIS|My Library|Calls & Conferences)$/;

  it("shows the rail whatever width the reader saved, with every control found by role and name", async () => {
    atWidth(width);
    useUIStore.setState({ sidebarCollapsed: false });
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const sidebar = screen.getByRole("complementary", { name: "Sidebar" });
    const nav = within(sidebar).getByRole("navigation", { name: "Main" });
    for (const name of ["Discover", "Ask IRIS", "My Library", "Calls & Conferences"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
    // The labels stay in the tree as screen-reader text, not display:none.
    for (const label of within(nav).getAllByText(LABELS)) {
      expect(label).toHaveClass("md:sr-only");
    }
    expect(within(sidebar).getByRole("button", { name: "Open sidebar" })).toBeInTheDocument();
    expect(within(sidebar).getByRole("button", { name: /^Notifications/ })).toBeInTheDocument();
    expect(within(sidebar).getByRole("button", { name: /account menu/ })).toBeInTheDocument();
    expect(sidebar).toHaveClass("md:w-rail");
    expect(sidebar).not.toHaveAttribute("inert");
  });

  it("leaves the page the rail's margin until the window reaches 1024 px", async () => {
    atWidth(width);
    useUIStore.setState({ sidebarCollapsed: false });
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const content = screen.getByRole("main").parentElement!;
    expect(content).toHaveClass("md:ml-rail");
    // The full sidebar's margin starts at lg (1024 px), not at md.
    expect(content).toHaveClass("lg:ml-60");
    expect(content).not.toHaveClass("md:ml-60");
  });

  it("shows a tooltip naming each link on hover and on keyboard focus", async () => {
    const user = userEvent.setup();
    atWidth(width);
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const navElement = await screen.findByRole("navigation", { name: "Main" });
    const nav = within(navElement);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    await user.hover(nav.getByRole("link", { name: "Ask IRIS" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Ask IRIS");
    await user.unhover(nav.getByRole("link", { name: "Ask IRIS" }));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    // Tab past the mark and the bell to the first link.
    while (!navElement.contains(document.activeElement)) await user.tab();
    const focused = document.activeElement as HTMLElement;
    expect(focused).toHaveAccessibleName("Discover");
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Discover");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("gives the IRIS mark, the bell and the account button a tooltip too", async () => {
    const user = userEvent.setup();
    atWidth(width);
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const sidebar = within(await screen.findByRole("complementary", { name: "Sidebar" }));
    await user.hover(sidebar.getByRole("button", { name: "Open sidebar" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Open sidebar");
    await user.hover(sidebar.getByRole("button", { name: /^Notifications/ }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Notifications");
    await user.hover(sidebar.getByRole("button", { name: /account menu/ }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Ana Adviser");
  });

  it("opens the full sidebar over the page from the IRIS mark, without saving a preference", async () => {
    const user = userEvent.setup();
    atWidth(width);
    useUIStore.setState({ sidebarCollapsed: false });
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const page = await screen.findByRole("heading", { name: "My Library" });
    await user.click(screen.getByRole("button", { name: "Open sidebar" }));

    const sidebar = screen.getByRole("complementary", { name: "Sidebar" });
    expect(sidebar).toHaveClass("md:w-60");
    const nav = within(sidebar).getByRole("navigation", { name: "Main" });
    for (const label of within(nav).getAllByText(LABELS)) {
      expect(label).not.toHaveClass("md:sr-only");
    }
    expect(within(sidebar).getByRole("button", { name: "Collapse sidebar" })).toHaveFocus();
    expect(page.closest("[inert]")).not.toBeNull();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);

    await user.keyboard("{Escape}");
    expect(useUIStore.getState().sidebarOpen).toBe(false);
    expect(screen.getByRole("button", { name: "Open sidebar" })).toHaveFocus();
  });

  it("closes the full sidebar when a link is chosen", async () => {
    const user = userEvent.setup();
    atWidth(width);
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await user.click(await screen.findByRole("button", { name: "Open sidebar" }));
    await user.click(within(screen.getByRole("navigation", { name: "Main" })).getByRole("link", { name: "Discover" }));

    expect(await screen.findByRole("heading", { name: "Discover" })).toBeInTheDocument();
    expect(useUIStore.getState().sidebarOpen).toBe(false);
    expect(screen.getByRole("button", { name: "Open sidebar" })).toBeInTheDocument();
  });

  it("closes the opened sidebar when the window widens to the desktop, and keeps the rail when it narrows", async () => {
    const user = userEvent.setup();
    const resizeTo = atWidth(width);
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await user.click(await screen.findByRole("button", { name: "Open sidebar" }));
    expect(useUIStore.getState().sidebarOpen).toBe(true);

    resizeTo(1280);
    expect(useUIStore.getState().sidebarOpen).toBe(false);
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();

    resizeTo(width);
    expect(screen.getByRole("button", { name: "Open sidebar" })).toBeInTheDocument();
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("has no serious or critical accessibility violations", async () => {
    atWidth(width);
    signIn(ROLES.RDCO, true);
    const { container } = renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    await expectNoBlockingA11yViolations(container);
  });
});

describe("the full sidebar from 1024 px (IR-1086)", () => {
  it("shows labels and keeps the reader's saved collapse, with the margin to match", async () => {
    atWidth(1024);
    useUIStore.setState({ sidebarCollapsed: false });
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const sidebar = screen.getByRole("complementary", { name: "Sidebar" });
    expect(sidebar).toHaveClass("md:w-60");
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
    expect(screen.getByRole("main").parentElement).toHaveClass("lg:ml-60");
  });

  it("still collapses to the rail when the reader chose that", async () => {
    atWidth(1280);
    useUIStore.setState({ sidebarCollapsed: true });
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    expect(screen.getByRole("complementary", { name: "Sidebar" })).toHaveClass("md:w-rail");
    expect(screen.getByRole("main").parentElement).not.toHaveClass("lg:ml-60");
  });
});

describe("the My Reviews route", () => {
  it("sends a user with no review work to Discover", async () => {
    signIn(ROLES.ADVISER, false);
    renderAt("/review");

    expect(await screen.findByRole("heading", { name: "Discover" })).toBeInTheDocument();
  });

  it("opens for a user with review work", async () => {
    signIn(ROLES.KTTO, true);
    renderAt("/review");

    expect(await screen.findByRole("heading", { name: "My Reviews" })).toBeInTheDocument();
  });
});
