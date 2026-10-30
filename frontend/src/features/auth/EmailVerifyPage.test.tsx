/**
 * Email verification announces its result (IR-538).
 *
 * Before IR-538 the screen swapped its heading silently once the activation
 * call settled, so a screen-reader user was left on "Verifying Email" for
 * good, and it drew its own copy of the brand panel. The result and, on
 * failure, its reason now change inside one polite live region, and the screen
 * renders through the shared entry frame.
 *
 * Queries go through the accessible tree, as in `LoginPage.test.tsx`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import { authApi } from "@/api/auth";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";

import EmailVerifyPage from "./EmailVerifyPage";

function renderVerify(route = "/activate/abc/def") {
  return renderScreen(
    <Routes>
      <Route path="/activate/:uidb64/:token" element={<EmailVerifyPage />} />
      <Route path="/login" element={<p>Sign-in screen</p>} />
      <Route path="/signup" element={<p>Register screen</p>} />
    </Routes>,
    { route },
  );
}

function activationSucceeds() {
  vi.spyOn(authApi, "activate").mockResolvedValue({ data: {} } as never);
}

function activationFails(detail?: string) {
  vi.spyOn(authApi, "activate").mockRejectedValue({
    response: { status: 400, data: detail ? { detail } : {} },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("while the link is being checked", () => {
  it("says so in the live region", () => {
    vi.spyOn(authApi, "activate").mockReturnValue(new Promise(() => {}) as never);
    renderVerify();

    expect(screen.getByRole("status")).toHaveTextContent("Verifying Email");
  });

  it("has no serious or critical accessibility violations", async () => {
    vi.spyOn(authApi, "activate").mockReturnValue(new Promise(() => {}) as never);
    const { container } = renderVerify();
    await expectNoBlockingA11yViolations(container);
  });
});

describe("a valid link", () => {
  it("announces the result through the live region", async () => {
    activationSucceeds();
    renderVerify();

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Email Verified"));
  });

  it("says RDCO approval follows, so the waiting screen is no surprise", async () => {
    activationSucceeds();
    renderVerify();

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/RDCO/));
  });

  it("offers sign in as a named link that reaches the sign-in screen", async () => {
    activationSucceeds();
    renderVerify();

    await userEvent.click(await screen.findByRole("link", { name: "Sign in" }));

    expect(screen.getByText("Sign-in screen")).toBeInTheDocument();
  });

  it("renders inside the shared entry frame", async () => {
    activationSucceeds();
    renderVerify();
    await screen.findByRole("heading", { level: 2, name: "Email Verified" });

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("has no serious or critical accessibility violations", async () => {
    activationSucceeds();
    const { container } = renderVerify();
    await screen.findByRole("heading", { level: 2, name: "Email Verified" });
    await expectNoBlockingA11yViolations(container);
  });
});

describe("an invalid link", () => {
  it("announces the failure with the server's reason in the same region", async () => {
    activationFails("Activation link has expired.");
    renderVerify();

    await waitFor(() => {
      const status = screen.getByRole("status");
      expect(status).toHaveTextContent("Verification Failed");
      expect(status).toHaveTextContent("Activation link has expired.");
    });
  });

  it("gives a reason of its own when the server sends none", async () => {
    activationFails();
    renderVerify();

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "This verification link is invalid or has already been used.",
      ),
    );
  });

  it("offers registering again and signing in as named links", async () => {
    activationFails();
    renderVerify();

    await userEvent.click(await screen.findByRole("link", { name: "Register again" }));
    expect(screen.getByText("Register screen")).toBeInTheDocument();
  });

  it("has a sign-in link too", async () => {
    activationFails();
    renderVerify();

    expect(await screen.findByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });

  it("has no serious or critical accessibility violations", async () => {
    activationFails();
    const { container } = renderVerify();
    await screen.findByRole("heading", { level: 2, name: "Verification Failed" });
    await expectNoBlockingA11yViolations(container);
  });
});
