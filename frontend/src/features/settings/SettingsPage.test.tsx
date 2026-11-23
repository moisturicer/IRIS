/**
 * The Settings password form, asserted through the accessible tree (IR-647).
 *
 * The API now applies the configured password policy, which can refuse one
 * password for several reasons at once. The form must say all of them.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes, useLocation } from "react-router-dom";

import { authApi } from "@/api/auth";
import { noticeApi } from "@/api/notice";
import { useAuthStore } from "@/store/auth.store";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import LoginPage from "@/features/auth/LoginPage";
import SettingsPage from "./SettingsPage";

beforeEach(() => {
  useAuthStore.setState({
    user: {
      id: 1, email: "reader@cit.edu", first_name: "Rea", last_name: "Der",
      role_name: "Student", college_name: "", department_name: "", course_name: "",
    } as never,
    isAuthenticated: true,
    authReady: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function changePassword(user: ReturnType<typeof userEvent.setup>, next: string) {
  await user.click(screen.getByRole("button", { name: "Account & security" }));
  await user.type(screen.getByLabelText("Current password"), "old-Passw0rd");
  await user.type(screen.getByLabelText(/^New password/), next);
  await user.type(screen.getByLabelText("Confirm new password"), next);
  await user.click(screen.getByRole("button", { name: "Change password" }));
}

describe("changing your password", () => {
  it("shows Change password as a pill that says what it is waiting for (IR-1088)", async () => {
    const user = userEvent.setup();
    renderScreen(<SettingsPage />, { route: "/settings" });
    await user.click(screen.getByRole("button", { name: "Account & security" }));

    const submit = screen.getByRole("button", { name: "Change password" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveClass("rounded-full");
    expect(submit).not.toHaveClass("uppercase");
    expect(submit).toHaveAccessibleDescription("Enter your current password and a new one.");

    await user.type(screen.getByLabelText("Current password"), "old-Passw0rd");
    await user.type(screen.getByLabelText(/^New password/), "new-Passw0rd");
    expect(screen.getByText(/^Password strength: /)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change password" })).toBeEnabled();
    expect(screen.queryByText("Enter your current password and a new one.")).not.toBeInTheDocument();
  });

  it("shows every reason the server refused the new password, not just the first", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "changePassword").mockRejectedValue({
      response: {
        status: 400,
        data: { new_password: ["This password is too common.", "This password is entirely numeric."] },
      },
    });
    const { container } = renderScreen(<SettingsPage />, { route: "/settings" });

    // Twelve digits: long enough to pass the form (IR-819), so the server decides.
    await changePassword(user, "123456789012");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "This password is too common. This password is entirely numeric.",
    );
    await expectNoBlockingA11yViolations(container);
  });

  it("still names a wrong current password", async () => {
    const user = userEvent.setup();
    vi.spyOn(authApi, "changePassword").mockRejectedValue({
      response: { status: 400, data: { old_password: ["Old password is incorrect."] } },
    });
    renderScreen(<SettingsPage />, { route: "/settings" });

    await changePassword(user, "Kalamansi-Tide-42");

    expect(await screen.findByRole("status")).toHaveTextContent("Old password is incorrect.");
  });

  it("signs out everywhere, this tab included, and says why on the sign-in screen", async () => {
    // ADR-045 §4 (IR-642): a change ends every session, so staying signed in
    // here would only fail on the next request.
    const user = userEvent.setup();
    vi.spyOn(authApi, "changePassword").mockResolvedValue({
      data: { code: "password_changed", detail: "Password changed. Sign in again with your new password." },
    } as never);
    renderScreen(
      <Routes>
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/login" element={<LoginPage />} />
      </Routes>,
      { route: "/settings" },
    );

    await changePassword(user, "Kalamansi-Tide-42");

    // Said in a dialog in front of the sign-in page (IR-1197).
    const dialog = await screen.findByRole("dialog", { name: "Password Changed" });
    expect(dialog).toHaveTextContent("Sign in again with your new password.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});

// IR-800: the notice shown is the server's current one, not text kept in the
// frontend, so the old IR-123 wording this test once looked for is gone with it.
it("shows the server's current notice beside the account's consent record (IR-800)", async () => {
  const user = userEvent.setup();
  useAuthStore.setState({
    user: { ...useAuthStore.getState().user!, consent_given: true, date_joined: "2026-09-01T00:00:00Z" },
  });
  vi.spyOn(noticeApi, "current").mockResolvedValue({
    data: { version: 6, text: "IRIS data notice\nAI companies may read your papers' text.", published_at: "2026-11-02T08:00:00Z" },
  } as never);
  renderScreen(<SettingsPage />, { route: "/settings" });

  await user.click(screen.getByRole("button", { name: "Data privacy & consent" }));

  expect(screen.getByText("Consent on record")).toBeVisible();
  const notice = screen.getByRole("region", { name: "Current data notice" });
  expect(await within(notice).findByText(/^IRIS data notice/)).toHaveTextContent("AI companies may read your papers' text.");
  expect(notice).toHaveTextContent("Version 6 · published Nov 2, 2026");
});

// IR-1085 (audit NAV-08): a Settings tab has an address, so it can be linked to
// and survives a reload.
describe("addressable tabs", () => {
  function Where() {
    const { pathname, search } = useLocation();
    return <p role="status" aria-label="Location">{pathname + search}</p>;
  }
  const renderAt = (route: string) =>
    renderScreen(<><SettingsPage /><Where /></>, { route });
  const where = () => screen.getByRole("status", { name: "Location" });
  const tab = (name: string) =>
    within(screen.getByRole("navigation", { name: "Settings sections" })).getByRole("button", { name });

  it("opens the Privacy tab at /settings?tab=privacy", () => {
    renderAt("/settings?tab=privacy");

    expect(tab("Data privacy & consent")).toHaveAttribute("aria-current", "page");
    expect(tab("Account & security")).not.toHaveAttribute("aria-current");
    expect(screen.getByText("No consent recorded")).toBeVisible();
  });

  it("opens the Role tab at /settings?tab=role", () => {
    renderAt("/settings?tab=role");

    expect(tab("Role & access")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("What your role lets you do in IRIS.")).toBeVisible();
  });

  it("updates the address when you switch tabs", async () => {
    const user = userEvent.setup();
    renderAt("/settings");

    await user.click(tab("Data privacy & consent"));
    expect(where()).toHaveTextContent("/settings?tab=privacy");
    expect(tab("Data privacy & consent")).toHaveAttribute("aria-current", "page");

    await user.click(tab("Role & access"));
    expect(where()).toHaveTextContent("/settings?tab=role");

    await user.click(tab("Account & security"));
    expect(where()).toHaveTextContent("/settings?tab=security");
    expect(screen.getByLabelText("Current password")).toBeVisible();
  });

  // Changed deliberately by IR-1304: Profile is the first section, so it is the
  // one a missing or unknown tab opens on (it was Account & security).
  it("opens on Profile when the tab is missing or unknown", () => {
    renderAt("/settings?tab=billing");

    expect(tab("Profile")).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("First name")).toBeVisible();
  });
});

// IR-933: Profile is its own page; IR-1304: Settings is where it is edited.
describe("settings and profile are separate", () => {
  it("has Profile first, then the account sections, opening on Profile", () => {
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    // Changed deliberately by IR-1245: Help is a section, not a link out; and by
    // IR-1304: Profile, where it is edited, is the first.
    expect(within(nav).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Profile", "Account & security", "Data privacy & consent", "Role & access", "Help",
    ]);
    expect(within(nav).getByRole("button", { name: "Profile" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("First name")).toBeVisible();
  });

  // IR-1245 replaces IR-1217's link: Help opened from Settings stays in Settings.
  it("opens Help as one of its sections, without leaving Settings (IR-1245)", async () => {
    function Where() {
      const { pathname, search } = useLocation();
      return <input readOnly aria-label="Location" value={pathname + search} />;
    }
    const user = userEvent.setup();
    renderScreen(
      <Routes>
        <Route path="/settings" element={<><SettingsPage /><Where /></>} />
        <Route path="*" element={<h1>Somewhere else</h1>} />
      </Routes>,
      { route: "/settings?tab=privacy" },
    );

    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    expect(within(nav).queryByRole("link", { name: "Help" })).not.toBeInTheDocument();
    await user.click(within(nav).getByRole("button", { name: "Help" }));

    expect(screen.getByLabelText("Location")).toHaveValue("/settings?tab=help");
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    expect(within(nav).getByRole("button", { name: "Help" })).toHaveAttribute("aria-current", "page");
    const contents = screen.getByRole("navigation", { name: "Help contents" });
    // Each contents entry jumps within this page, keeping Settings' address.
    expect(within(contents).getByRole("link", { name: "Finding research" })).toHaveAttribute("href", "#discover");
    expect(screen.getByRole("region", { name: "Finding research" })).toBeInTheDocument();
  });

  // jsdom draws no layout, so this pins the rule that keeps every section in
  // view on a phone; the screen itself is checked by hand (IR-1246).
  it("wraps its sections on a narrow screen rather than scrolling one out of view (IR-1246)", () => {
    renderScreen(<SettingsPage />, { route: "/settings?tab=help" });

    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    expect(nav).toHaveClass("flex-wrap", "lg:flex-col");
    expect(nav).not.toHaveClass("overflow-x-auto");
    expect(within(nav).getByRole("button", { name: "Help" })).toHaveAttribute("aria-current", "page");
  });

  it("opens straight on Help from its address, and on the section it names", () => {
    const original = Element.prototype.scrollIntoView;
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    try {
      renderScreen(<SettingsPage />, { route: "/settings?tab=help#discover" });

      expect(screen.getByRole("button", { name: "Help" })).toHaveAttribute("aria-current", "page");
      expect(scrolled).toHaveBeenCalled();
      expect(scrolled.mock.contexts[0]).toBe(screen.getByRole("region", { name: "Finding research" }));
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  // Changed deliberately by IR-1304: Settings now holds the editing (it used to
  // point away from it), and still links to the Profile it changes.
  it("links to the Profile preview, and holds the editing of it", () => {
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(screen.getByRole("link", { name: "Your profile" })).toHaveAttribute("href", "/profile");
    expect(screen.getByLabelText("Bio")).toBeVisible();
    expect(screen.queryByRole("link", { name: "View my profile" })).not.toBeInTheDocument();
  });

  it("shows the sign-in email as read-only, managed by the university", () => {
    renderScreen(<SettingsPage />, { route: "/settings?tab=security" });

    expect(screen.getByLabelText("Sign-in email")).toHaveValue("reader@cit.edu");
    expect(screen.getByLabelText("Sign-in email")).toHaveAttribute("readonly");
  });
});
