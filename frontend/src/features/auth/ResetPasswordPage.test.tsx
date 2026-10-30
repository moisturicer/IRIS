/**
 * Choosing a new password from an emailed link (IR-642, ADR-045 §3, §7).
 *
 * The link carries its token in the URL fragment, which no server or proxy
 * log sees. The page reads it once, strips it from the address bar at once,
 * and spends it only when the person submits: opening the page -- or a mail
 * scanner prefetching it -- changes nothing. Queries go through the
 * accessible tree only.
 */
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, renderScreen, screen, userEvent, waitFor } from "@/test/render";

import ResetPasswordPage from "./ResetPasswordPage";

const TOKEN = "a".repeat(43);
const INVALID_LINK = {
  code: "invalid_link",
  detail: "This link is invalid or no longer available. Request a new email.",
};

function failure(status: number, data: unknown) {
  return Object.assign(new Error("request failed"), { response: { status, data } });
}

function openLink(fragment = `#token=${TOKEN}`) {
  window.history.replaceState(null, "", `/password/reset${fragment}`);
  return renderScreen(<ResetPasswordPage />, { route: `/password/reset${fragment}` });
}

async function choose(user: ReturnType<typeof userEvent.setup>, password = "Brand-new-pass-2", confirm = password) {
  await user.type(screen.getByLabelText("New password"), password);
  await user.type(screen.getByLabelText("Confirm new password"), confirm);
  await user.click(screen.getByRole("button", { name: "Set new password" }));
}

beforeEach(() => {
  document.head.querySelectorAll('meta[name="referrer"]').forEach((m) => m.remove());
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("the reset-password screen", () => {
  it("strips the token from the address bar on arrival and spends nothing until submit", () => {
    const confirm = vi.spyOn(authApi, "confirmPasswordReset");
    openLink();
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/password/reset");
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
  });

  it("keeps the token through React's development double mount", async () => {
    // main.tsx renders under StrictMode, which mounts every component twice
    // in development; the second mount must not find the link already spent.
    const user = userEvent.setup();
    const confirm = vi.spyOn(authApi, "confirmPasswordReset").mockResolvedValue({
      data: { code: "password_reset", detail: "Password updated. Sign in with your new password." },
    } as never);
    window.history.replaceState(null, "", `/password/reset#token=${TOKEN}`);
    renderScreen(<StrictMode><ResetPasswordPage /></StrictMode>, { route: `/password/reset#token=${TOKEN}` });

    expect(window.location.hash).toBe("");
    await choose(user);
    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({ token: TOKEN }));
  });

  it("sends no referrer while open", () => {
    const { unmount } = openLink();
    expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute("content", "no-referrer");
    unmount();
    expect(document.head.querySelector('meta[name="referrer"]')).toBeNull();
  });

  it("labels both fields, offers show/hide and states the policy, with no blocking violations", async () => {
    const user = userEvent.setup();
    const { container } = openLink();
    const field = screen.getByLabelText("New password");
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAccessibleDescription(/at least 8 characters/i);
    await user.click(screen.getByRole("button", { name: "Show new password" }));
    expect(field).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("Confirm new password")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("sets the password and hands the person back to sign-in, without signing them in", async () => {
    const confirm = vi.spyOn(authApi, "confirmPasswordReset").mockResolvedValue({
      data: { code: "password_reset", detail: "Password updated. Sign in with your new password." },
    } as never);
    const user = userEvent.setup();
    openLink();

    await choose(user);

    expect(confirm).toHaveBeenCalledWith({
      token: TOKEN, new_password: "Brand-new-pass-2", confirm_password: "Brand-new-pass-2",
    });
    const heading = await screen.findByRole("heading", { name: "Password updated" });
    expect(heading).toHaveFocus();
    expect(screen.getByText("Password updated. Sign in with your new password.")).toBeInTheDocument();
    expect(screen.getByText(/approval and any account restrictions still apply/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to sign in" })).toHaveAttribute("href", "/login");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
  });

  it("shows the server's password errors on their fields and focuses a summary, keeping the link", async () => {
    const confirm = vi.spyOn(authApi, "confirmPasswordReset")
      .mockRejectedValueOnce(failure(400, {
        code: "validation_error",
        errors: {
          new_password: ["This password is too common."],
          confirm_password: ["Passwords do not match."],
        },
      }) as never)
      .mockResolvedValueOnce({ data: { code: "password_reset", detail: "Password updated. Sign in with your new password." } } as never);
    const user = userEvent.setup();
    openLink();

    await choose(user, "password", "passwordX");

    const summary = await screen.findByRole("alert");
    expect(summary).toHaveFocus();
    expect(summary).toHaveTextContent("This password is too common.");
    expect(screen.getByLabelText("New password")).toHaveAccessibleDescription("This password is too common.");
    expect(screen.getByLabelText("New password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Confirm new password")).toHaveAccessibleDescription("Passwords do not match.");

    await user.clear(screen.getByLabelText("New password"));
    await user.clear(screen.getByLabelText("Confirm new password"));
    await choose(user);
    expect(await screen.findByRole("heading", { name: "Password updated" })).toBeInTheDocument();
    expect(confirm.mock.calls[1][0].token).toBe(TOKEN);
  });

  it("asks for both fields before contacting the server", async () => {
    const confirm = vi.spyOn(authApi, "confirmPasswordReset");
    const user = userEvent.setup();
    openLink();
    await user.click(screen.getByRole("button", { name: "Set new password" }));
    await waitFor(() =>
      expect(screen.getByLabelText("New password")).toHaveAccessibleDescription("Enter a new password."));
    expect(confirm).not.toHaveBeenCalled();
  });

  it("gives the same guidance for an invalid, expired or used link, with a way to a new email", async () => {
    vi.spyOn(authApi, "confirmPasswordReset").mockRejectedValue(failure(400, INVALID_LINK) as never);
    const user = userEvent.setup();
    const { container } = openLink();

    await choose(user);

    const heading = await screen.findByRole("heading", { name: "This link can't be used" });
    expect(heading).toHaveFocus();
    expect(screen.getByText(INVALID_LINK.detail)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new email" })).toHaveAttribute("href", "/password/forgot");
    expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows the invalid-link guidance straight away when the link carries no token", () => {
    openLink("");
    expect(screen.getByRole("heading", { name: "This link can't be used" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Request a new email" })).toBeInTheDocument();
  });

  it("keeps the form after a network failure or 503 so the same link can be retried", async () => {
    const confirm = vi.spyOn(authApi, "confirmPasswordReset")
      .mockRejectedValueOnce(new Error("Network Error") as never)
      .mockRejectedValueOnce(failure(503, { code: "temporarily_unavailable", retry_after: 60 }) as never);
    const user = userEvent.setup();
    openLink();

    await choose(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/may not have reached IRIS/i);
    expect(screen.getByLabelText("New password")).toHaveValue("Brand-new-pass-2");

    await user.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/try again in 60 seconds/i);
    expect(confirm).toHaveBeenCalledTimes(2);
    expect(confirm.mock.calls.every(([body]) => body.token === TOKEN)).toBe(true);
  });

  it("states the server's delay when rate limited", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(authApi, "confirmPasswordReset")
      .mockRejectedValue(failure(429, { code: "rate_limited", retry_after: 120 }) as never);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    openLink();
    await choose(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/too many requests.*try again in 120 seconds/i);
    expect(screen.getByRole("button", { name: /set new password/i })).toBeDisabled();
    await act(async () => { vi.advanceTimersByTime(120_000); });
    expect(screen.getByRole("button", { name: "Set new password" })).toBeEnabled();
  });
});
