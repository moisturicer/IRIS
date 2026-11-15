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

    await changePassword(user, "12345678");

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

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Password changed");
    expect(alert).toHaveTextContent("Sign in again with your new password.");
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();
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

  it("opens on Account & security when the tab is missing or unknown", () => {
    renderAt("/settings?tab=billing");

    expect(tab("Account & security")).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Current password")).toBeVisible();
  });
});

// IR-933: Profile is its own page; Settings keeps the account.
describe("settings and profile are separate", () => {
  it("has the account sections only, opening on Account & security", () => {
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
    const nav = screen.getByRole("navigation", { name: "Settings sections" });
    expect(within(nav).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Account & security", "Data privacy & consent", "Role & access",
    ]);
    expect(within(nav).getByRole("button", { name: "Account & security" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByLabelText("Current password")).toBeVisible();
  });

  it("points to the Profile instead of holding it", () => {
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(screen.getByRole("link", { name: "Your profile" })).toHaveAttribute("href", "/profile");
    expect(screen.queryByLabelText("Bio")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View my profile" })).not.toBeInTheDocument();
  });

  it("shows the sign-in email as read-only, managed by the university", () => {
    renderScreen(<SettingsPage />, { route: "/settings" });

    expect(screen.getByLabelText("Sign-in email")).toHaveValue("reader@cit.edu");
    expect(screen.getByLabelText("Sign-in email")).toHaveAttribute("readonly");
  });
});
