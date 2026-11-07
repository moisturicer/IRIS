/**
 * Verifying an email address from an emailed link (IR-643, ADR-045 §3, §7).
 *
 * The link carries its token in the URL fragment, which no server or proxy
 * log sees. The page reads it once, strips it from the address bar at once,
 * and spends it only when the person presses "Verify email": opening the page
 * -- or a mail scanner prefetching it -- changes nothing. Old `/activate`
 * links are retired, so they land on the same guidance as any unusable link.
 * Queries go through the accessible tree only.
 */
import { StrictMode } from "react";
import { Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, renderScreen, screen, userEvent } from "@/test/render";

import VerifyEmailPage from "./VerifyEmailPage";

const TOKEN = "a".repeat(43);
const VERIFIED = { code: "email_verified", detail: "Email verified. Return to sign-in." };
const INVALID_LINK = {
  code: "invalid_link",
  detail: "This link is invalid or no longer available. Request a new email.",
};

function failure(status: number, data: unknown) {
  return Object.assign(new Error("request failed"), { response: { status, data } });
}

function open(address = `/verify-email#token=${TOKEN}`) {
  window.history.replaceState(null, "", address);
  return renderScreen(
    <Routes>
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/activate" element={<VerifyEmailPage />} />
      <Route path="/activate/:uidb64/:token" element={<VerifyEmailPage />} />
    </Routes>,
    { route: address },
  );
}

const verifyButton = () => screen.getByRole("button", { name: /verify email/i });

beforeEach(() => {
  document.head.querySelectorAll('meta[name="referrer"]').forEach((m) => m.remove());
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("the verify-email screen", () => {
  it("strips the token from the address bar on arrival and verifies nothing until the button", async () => {
    const confirm = vi.spyOn(authApi, "confirmVerification");
    const { container } = open();

    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/verify-email");
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Verify your email" })).toBeInTheDocument();
    expect(screen.getByText(/does not sign you in/i)).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("keeps the token through React's development double mount", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(authApi, "confirmVerification").mockResolvedValue({ data: VERIFIED } as never);
    window.history.replaceState(null, "", `/verify-email#token=${TOKEN}`);
    renderScreen(<StrictMode><VerifyEmailPage /></StrictMode>, { route: `/verify-email#token=${TOKEN}` });

    await user.click(verifyButton());
    expect(confirm).toHaveBeenCalledWith(TOKEN);
  });

  it("sends no referrer while open", () => {
    const { unmount } = open();
    expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute("content", "no-referrer");
    unmount();
    expect(document.head.querySelector('meta[name="referrer"]')).toBeNull();
  });

  it("verifies on the button, says approval may still be pending, and returns to sign-in", async () => {
    vi.spyOn(authApi, "confirmVerification").mockResolvedValue({ data: VERIFIED } as never);
    const user = userEvent.setup();
    const { container } = open();

    await user.click(verifyButton());

    const heading = await screen.findByRole("heading", { name: "Email verified" });
    expect(heading).toHaveFocus();
    expect(screen.getByText(VERIFIED.detail)).toBeInTheDocument();
    expect(screen.getByText(/may still need to approve your account/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to sign in" })).toHaveAttribute("href", "/login");
    await expectNoBlockingA11yViolations(container);
  });

  it("gives one guidance for an invalid, expired, used or replaced link, with a way to a new email", async () => {
    vi.spyOn(authApi, "confirmVerification").mockRejectedValue(failure(400, INVALID_LINK) as never);
    const user = userEvent.setup();
    const { container } = open();

    await user.click(verifyButton());

    const heading = await screen.findByRole("heading", { name: "This link can't be used" });
    expect(heading).toHaveFocus();
    expect(screen.getByText(INVALID_LINK.detail)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resend verification email" }))
      .toHaveAttribute("href", "/verify-email/resend");
    expect(screen.queryByRole("button", { name: /verify email/i })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows that guidance straight away for a link with no token", () => {
    open("/verify-email");
    expect(screen.getByRole("heading", { name: "This link can't be used" })).toBeInTheDocument();
  });

  it.each([
    ["the fragment form IR-928 emailed", "/activate#uid=Mjc&token=abc-123"],
    ["the path form emailed before IR-928", "/activate/Mjc/abc-123"],
  ])("retires %s: guidance, no request, and the secret gone from the address bar", (_label, address) => {
    const confirm = vi.spyOn(authApi, "confirmVerification");
    open(address);

    expect(screen.getByRole("heading", { name: "This link can't be used" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Resend verification email" })).toBeInTheDocument();
    expect(confirm).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe("/verify-email");
    expect(window.location.hash).toBe("");
  });

  it("keeps the button after a network failure so the same link is retried, never claiming it failed", async () => {
    const confirm = vi.spyOn(authApi, "confirmVerification")
      .mockRejectedValueOnce(new Error("Network Error") as never)
      .mockResolvedValueOnce({ data: VERIFIED } as never);
    const user = userEvent.setup();
    open();

    await user.click(verifyButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/may not have reached IRIS/i);
    expect(alert).not.toHaveTextContent(/failed/i);

    await user.click(verifyButton());
    expect(await screen.findByRole("heading", { name: "Email verified" })).toBeInTheDocument();
    expect(confirm.mock.calls).toEqual([[TOKEN], [TOKEN]]);
  });

  it("waits out the server's delay after a 429 or 503", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(authApi, "confirmVerification")
      .mockRejectedValue(failure(429, { code: "rate_limited", retry_after: 20 }) as never);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    open();

    await user.click(verifyButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(/too many requests.*try again in 20 seconds/i);
    expect(verifyButton()).toBeDisabled();
    await act(async () => { vi.advanceTimersByTime(20_000); });
    expect(verifyButton()).toBeEnabled();
  });

  it("works at phone width with the keyboard alone", async () => {
    vi.spyOn(authApi, "confirmVerification").mockResolvedValue({ data: VERIFIED } as never);
    window.innerWidth = 320;
    const user = userEvent.setup();
    open();

    await user.tab();
    expect(verifyButton()).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { name: "Email verified" })).toHaveFocus();
  });
});
