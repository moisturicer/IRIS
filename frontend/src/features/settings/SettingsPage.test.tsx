/**
 * The Settings password form, asserted through the accessible tree (IR-647).
 *
 * The API now applies the configured password policy, which can refuse one
 * password for several reasons at once. The form must say all of them.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { useAuthStore } from "@/store/auth.store";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent } from "@/test/render";

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
});

it("distinguishes the current disclosure notice from historical account consent (IR-123)", async () => {
  const user = userEvent.setup();
  useAuthStore.setState({
    user: { ...useAuthStore.getState().user!, consent_given: true, date_joined: "2026-09-01T00:00:00Z" },
  });
  renderScreen(<SettingsPage />, { route: "/settings" });

  await user.click(screen.getByRole("button", { name: "Data privacy & consent" }));

  expect(screen.getByText("Consent on record")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Current disclosure notice" })).toBeVisible();
  expect(screen.getByText(/does not confirm.*accepted this revised notice/i)).toBeVisible();
  expect(screen.queryByText("What you agreed to")).not.toBeInTheDocument();
  expect(screen.getByText(/external AI providers outside CIT-U/i)).toBeVisible();
});
