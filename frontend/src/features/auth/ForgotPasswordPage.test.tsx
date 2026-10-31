/**
 * Asking for a password-reset email (IR-642, ADR-045 §7).
 *
 * The server answers every address the same way, so this screen can only ever
 * say "if this address is eligible"; what it controls is everything around
 * that answer -- the pending state, the cooldown, and what a failure means.
 * Queries go through the accessible tree only.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";

import { authApi } from "@/api/auth";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";

import ForgotPasswordPage from "./ForgotPasswordPage";

const RECEIVED = {
  code: "request_received",
  detail: "If this address is eligible, an email will arrive shortly. You can try again after 60 seconds.",
  retry_after: 60,
};

function failure(status: number, data: unknown) {
  return Object.assign(new Error("request failed"), { response: { status, data } });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

async function submit(user: ReturnType<typeof userEvent.setup>, email = "reader@cit.edu") {
  await user.clear(screen.getByRole("textbox", { name: /email address/i }));
  await user.type(screen.getByRole("textbox", { name: /email address/i }), email);
  await user.click(screen.getByRole("button", { name: "Send reset email" }));
}

describe("the forgot-password screen", () => {
  it("has a labelled email field and no blocking accessibility violations", async () => {
    const { container } = renderScreen(<ForgotPasswordPage />, { route: "/password/forgot" });
    expect(screen.getByRole("heading", { name: "Reset your password" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /email address/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toHaveAttribute("href", "/login");
    await expectNoBlockingA11yViolations(container);
  });

  it("explains an invalid address on the field itself, without asking the server", async () => {
    const request = vi.spyOn(authApi, "requestPasswordReset");
    const user = userEvent.setup();
    renderScreen(<ForgotPasswordPage />, { route: "/password/forgot" });

    await submit(user, "not-an-email");

    const field = screen.getByRole("textbox", { name: /email address/i });
    await waitFor(() => expect(field).toHaveAccessibleDescription("Enter a valid email address."));
    expect(field).toHaveAttribute("aria-invalid", "true");
    // ADR-045 §7: focus goes to what needs fixing, not left on the button.
    expect(field).toHaveFocus();
    expect(request).not.toHaveBeenCalled();
  });

  it("announces the pending request and blocks a second submit while it runs", async () => {
    const pending = deferred<{ data: typeof RECEIVED }>();
    const request = vi.spyOn(authApi, "requestPasswordReset").mockReturnValue(pending.promise as never);
    const user = userEvent.setup();
    renderScreen(<ForgotPasswordPage />, { route: "/password/forgot" });

    await submit(user);

    expect(screen.getByRole("status")).toHaveTextContent("Sending…");
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
    expect(request).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledWith("reader@cit.edu");
    await act(async () => pending.resolve({ data: RECEIVED }));
  });

  it("confirms generically, focuses the confirmation and counts down to the next request", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(authApi, "requestPasswordReset").mockResolvedValue({ data: RECEIVED } as never);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderScreen(<ForgotPasswordPage />, { route: "/password/forgot" });

    await submit(user);

    const heading = await screen.findByRole("heading", { name: "Check your email" });
    expect(heading).toHaveFocus();
    expect(screen.getByText(RECEIVED.detail)).toBeInTheDocument();
    expect(screen.getByText(/Check spam, try again after 60 seconds, or contact RDCO or your department administrator\./))
      .toBeInTheDocument();
    const again = screen.getByRole("button", { name: /send another email/i });
    expect(again).toBeDisabled();
    expect(again).toHaveAccessibleName(/60 seconds/);

    await act(async () => { vi.advanceTimersByTime(30_000); });
    expect(screen.getByRole("button", { name: /send another email/i })).toHaveAccessibleName(/30 seconds/);
    // The countdown is visible, not announced every second.
    expect(screen.queryByText(/you can request another email now/i)).not.toBeInTheDocument();

    await act(async () => { vi.advanceTimersByTime(30_000); });
    expect(screen.getByRole("button", { name: "Send another email" })).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent("You can request another email now.");
  });

  it("keeps the address after a network failure and says the outcome is unknown", async () => {
    vi.spyOn(authApi, "requestPasswordReset").mockRejectedValue(new Error("Network Error") as never);
    const user = userEvent.setup();
    renderScreen(<ForgotPasswordPage />, { route: "/password/forgot" });

    await submit(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/may not have reached IRIS/i);
    expect(alert).not.toHaveTextContent(/failed to send/i);
    await waitFor(() => expect(alert).toHaveFocus());
    expect(screen.getByRole("textbox", { name: /email address/i })).toHaveValue("reader@cit.edu");
    expect(screen.getByRole("button", { name: "Send reset email" })).toBeEnabled();
  });

  it("waits out the server's delay after a 503 or a 429 before allowing a retry", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const request = vi.spyOn(authApi, "requestPasswordReset")
      .mockRejectedValueOnce(failure(503, { code: "temporarily_unavailable", retry_after: 60 }) as never)
      .mockRejectedValueOnce(failure(429, { code: "rate_limited", retry_after: 5 }) as never);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderScreen(<ForgotPasswordPage />, { route: "/password/forgot" });

    await submit(user);
    expect(await screen.findByRole("alert")).toHaveTextContent(/try again in 60 seconds/i);
    expect(screen.getByRole("textbox", { name: /email address/i })).toHaveValue("reader@cit.edu");
    expect(screen.getByRole("button", { name: /send reset email/i })).toBeDisabled();

    await act(async () => { vi.advanceTimersByTime(60_000); });
    await user.click(screen.getByRole("button", { name: "Send reset email" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/too many requests.*try again in 5 seconds/i);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("works at phone width with the keyboard alone", async () => {
    vi.spyOn(authApi, "requestPasswordReset").mockResolvedValue({ data: RECEIVED } as never);
    window.innerWidth = 320;
    const user = userEvent.setup();
    renderScreen(<ForgotPasswordPage />, { route: "/password/forgot" });

    await user.tab();
    expect(screen.getByRole("textbox", { name: /email address/i })).toHaveFocus();
    await user.keyboard("reader@cit.edu{Enter}");
    expect(await screen.findByRole("heading", { name: "Check your email" })).toHaveFocus();
  });
});
