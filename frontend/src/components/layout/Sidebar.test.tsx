/**
 * The sidebar (IR-413, spec §4.1-§4.2).
 *
 * One short list, My Reviews only for a user with review work, RDCO's
 * Administration group, and an account menu holding Settings & Profile, Help
 * and Sign out. Below `md` it is a drawer that is out of the tab order while
 * closed, takes focus when opened, and closes on Escape.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
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
          { path: "/settings", element: <h1>Settings &amp; Profile</h1> },
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

  it("names RDCO's Administration group and counts its waiting role requests", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { count: 3, results: [] } } as never);
    signIn(ROLES.RDCO, true);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    const admin = screen.getByRole("list", { name: "Administration" });
    expect(within(admin).getAllByRole("link").map((l) => l.textContent?.trim())[0]).toBe("Import Records");
    expect(await within(admin).findByRole("link", { name: "Role Requests, 3 waiting" })).toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });

  it("collapses and expands from one control", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    await user.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
    await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);
  });

  it("has no serious or critical accessibility violations", async () => {
    signIn(ROLES.RDCO, true);
    const { container } = renderAt("/records/mine");

    await screen.findByRole("heading", { name: "My Library" });
    await expectNoBlockingA11yViolations(container);
  });
});

describe("the account menu", () => {
  it("holds Settings & Profile, Help and Sign out", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    const trigger = await screen.findByRole("button", { name: /Ana Adviser.*account menu/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Settings & Profile" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("link", { name: "Help" })).toHaveAttribute("href", "/help");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("opens Settings & Profile and closes behind it", async () => {
    const user = userEvent.setup();
    signIn(ROLES.STUDENT);
    renderAt("/records/mine");

    await user.click(await screen.findByRole("button", { name: /account menu/ }));
    await user.click(screen.getByRole("link", { name: "Settings & Profile" }));

    expect(await screen.findByRole("heading", { name: "Settings & Profile" })).toBeInTheDocument();
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
