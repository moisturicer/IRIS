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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import { authApi } from "@/api/auth";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import EmailVerifyPage from "./EmailVerifyPage";

/**
 * The link as emailed since IR-928: the secret is in the fragment, which the
 * browser never sends. The page reads `window.location`, so the address is set
 * there as well as in the router.
 */
const FRAGMENT = "#uid=abc&token=def-123";

function renderVerify(route = `/activate${FRAGMENT}`) {
  window.history.replaceState(null, "", route);
  return renderScreen(
    <Routes>
      <Route path="/activate" element={<EmailVerifyPage />} />
      {/* Deprecated (IR-928): links emailed before the token moved to the fragment. */}
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

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

/**
 * The secret is read once from the fragment (IR-928, ASVS 8.3.1), posted in a
 * body, and gone from the address bar; the reset page does the same (ADR-045 §3).
 */
describe("a link with its secret in the fragment", () => {
  it("posts the uid and token it carries", async () => {
    const activate = vi.spyOn(authApi, "activate").mockResolvedValue({ data: {} } as never);
    renderVerify();

    await waitFor(() => expect(activate).toHaveBeenCalledWith("abc", "def-123"));
  });

  it("removes the fragment from the address bar", async () => {
    activationSucceeds();
    renderVerify();
    await screen.findByRole("heading", { level: 2, name: "Email Verified" });

    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/activate");
  });

  it("asks the browser to send no referrer while it holds the secret", async () => {
    activationSucceeds();
    renderVerify();
    await screen.findByRole("heading", { level: 2, name: "Email Verified" });

    expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute("content", "no-referrer");
  });

  it.each([
    ["no fragment", "/activate"],
    ["only a uid", "/activate#uid=abc"],
    ["only a token", "/activate#token=def-123"],
    ["an empty token", "/activate#uid=abc&token="],
    ["other characters", "/activate#uid=abc&token=de%20f"],
    ["extra fields", "/activate#uid=abc&token=def-123&next=/admin"],
  ])("with %s, makes no request and says the link is invalid", async (_name, route) => {
    const activate = vi.spyOn(authApi, "activate").mockResolvedValue({ data: {} } as never);
    renderVerify(route);

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Verification Failed"));
    expect(screen.getByRole("status")).toHaveTextContent("Invalid verification link.");
    expect(activate).not.toHaveBeenCalled();
  });
});

/**
 * Links emailed before IR-928 carry the secret in the path. They keep working
 * until their tokens expire, but the page sends the secret in a body and
 * replaces the address, so the old shape no longer reaches the server's path.
 */
describe("a link emailed before the secret moved to the fragment (deprecated)", () => {
  it("posts the uid and token from the path in a body", async () => {
    const activate = vi.spyOn(authApi, "activate").mockResolvedValue({ data: {} } as never);
    renderVerify("/activate/abc/def-123");

    await waitFor(() => expect(activate).toHaveBeenCalledWith("abc", "def-123"));
    await screen.findByRole("heading", { level: 2, name: "Email Verified" });
  });

  it("replaces the secret in the address bar", async () => {
    activationSucceeds();
    renderVerify("/activate/abc/def-123");
    await screen.findByRole("heading", { level: 2, name: "Email Verified" });

    expect(window.location.pathname).toBe("/activate");
    expect(window.location.href).not.toContain("def-123");
  });
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

  it("says an administrator's approval follows, so the waiting screen is no surprise", async () => {
    activationSucceeds();
    renderVerify();

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/An administrator now reviews/));
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

/**
 * The Dossier frame, without its lede (IR-710, IR-704 story 51): the result
 * sits on the folder's sheet under the masthead, so verification reads as the
 * same flow as sign in. The sheet already offers every way on, so the
 * masthead carries no cross-link of its own.
 */
describe.each([
  { result: "verified", title: "Email Verified", arrange: activationSucceeds },
  { result: "failed", title: "Verification Failed", arrange: () => activationFails() },
  {
    result: "expired",
    title: "Verification Failed",
    arrange: () => activationFails("Activation link has expired."),
  },
])("the frame for a $result link", ({ title, arrange }) => {
  async function renderResult() {
    arrange();
    const view = renderVerify();
    await screen.findByRole("heading", { level: 2, name: title });
    return view;
  }

  it("names IRIS and the pilot institution in the masthead, the page's only top-level heading", async () => {
    await renderResult();

    const [masthead, ...others] = screen.getAllByRole("heading", { level: 1 });
    expect(others).toEqual([]);
    expect(masthead).toHaveAccessibleName(/IRIS/);
    expect(masthead).toHaveAccessibleName(/Cebu Institute of Technology/);
  });

  it("labels the sheet with an Email verification tab, and draws no brand panel", async () => {
    await renderResult();

    expect(screen.getByText("Email verification")).toBeInTheDocument();
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("shows no headline or lede sentence", async () => {
    await renderResult();

    expect(screen.queryByText(/Your research has/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^IRIS is CIT-U's system/)).not.toBeInTheDocument();
  });

  it("offers privacy and terms in the shared entry footer", async () => {
    await renderResult();

    const footer = screen.getByRole("contentinfo");
    expect(footer).not.toHaveTextContent("Pilot institution:");
    expect(within(footer).getByRole("link", { name: "Data privacy" })).toBeInTheDocument();
    expect(within(footer).getByRole("link", { name: "Terms" })).toBeInTheDocument();
  });
});
