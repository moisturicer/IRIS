/**
 * Asking for another verification email (IR-643, ADR-045 §7).
 *
 * The form is the one "Forgot password?" uses (`EmailRequestForm`, whose
 * timing and failure states `ForgotPasswordPage.test.tsx` covers); these cases
 * pin what is this screen's own: its endpoint, its words, and an address
 * carried over from the screen where the person typed it.
 */
import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent } from "@/test/render";

import ResendVerificationPage from "./ResendVerificationPage";

const RECEIVED = {
  code: "request_received",
  detail: "If this address is eligible, an email will arrive shortly. You can try again after 60 seconds.",
  retry_after: 60,
};

afterEach(() => {
  vi.restoreAllMocks();
});

const emailField = () => screen.getByRole("textbox", { name: /email address/i });

describe("the resend-verification screen", () => {
  it("says no new registration is needed, with a labelled field and no blocking violations", async () => {
    const { container } = renderScreen(<ResendVerificationPage />, { route: "/verify-email/resend" });
    expect(screen.getByRole("heading", { name: "Send a new verification email" })).toBeInTheDocument();
    expect(screen.getByText(/do not need to register again/i)).toBeInTheDocument();
    expect(emailField()).toHaveValue("");
    await expectNoBlockingA11yViolations(container);
  });

  it("asks the verification endpoint and confirms generically, with the ADR's delivery guidance", async () => {
    const resend = vi.spyOn(authApi, "resendVerification").mockResolvedValue({ data: RECEIVED } as never);
    const reset = vi.spyOn(authApi, "requestPasswordReset");
    const user = userEvent.setup();
    renderScreen(<ResendVerificationPage />, { route: "/verify-email/resend" });

    await user.type(emailField(), "  reader@cit.edu ");
    await user.click(screen.getByRole("button", { name: "Send verification email" }));

    expect(await screen.findByRole("heading", { name: "Check your email" })).toHaveFocus();
    expect(resend).toHaveBeenCalledWith("reader@cit.edu");
    expect(reset).not.toHaveBeenCalled();
    expect(screen.getByText(RECEIVED.detail)).toBeInTheDocument();
    expect(screen.getByText(
      "Email may take a few minutes. Check spam, try again after 60 seconds, or contact RDCO or your "
      + "department administrator.",
    )).toBeInTheDocument();
  });

  it("starts with the address the person typed on the screen that sent them here", () => {
    renderScreen(
      <Routes><Route path="/verify-email/resend" element={<ResendVerificationPage />} /></Routes>,
      { route: "/verify-email/resend", state: { email: "typed@cit.edu" } },
    );
    expect(emailField()).toHaveValue("typed@cit.edu");
  });
});
