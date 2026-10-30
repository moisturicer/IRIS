/**
 * The login screen, asserted through the accessible tree (IR-210).
 *
 * This file is the tracer bullet for the frontend test seam. IR-204 repaired
 * this screen's accessibility by hand and recorded the result in a PR body;
 * that evidence was true when written and stopped being checkable the moment
 * the file was next edited. These tests convert it into a standing assertion.
 *
 * **Every query goes through the accessible tree** -- by role and accessible
 * name, or by label. None by class name, `data-testid`, or component internals.
 * That is not a style rule: the accessible tree is what a screen reader walks,
 * so a test that can still find a control after its label association breaks is
 * a test that cannot detect the bug this suite exists to catch.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { Route, Routes, useLocation } from "react-router-dom";

import { authApi } from "@/api/auth";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore } from "@/store/ui.store";
import { getRoleDashboardPath } from "@/lib/roleDashboard";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { FIXTURE_ROLE, makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";

import LoginPage from "./LoginPage";

describe("the login screen", () => {
  it("gives every control an accessible name", () => {
    renderScreen(<LoginPage />, { route: "/login" });

    // `getByRole` resolves the name the way an assistive technology would --
    // through the <label for>, not the visible text's position on screen.
    expect(screen.getByRole("textbox", { name: "Email Address" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign In" })).toBeInTheDocument();

    // A password input has no implicit ARIA role, so it is unreachable by role
    // and is queried by its label instead. Still the accessible tree.
    expect(screen.getByLabelText("Password")).toBeInTheDocument();

    // The show/hide toggle's visible text is "Show", but 2.5.3 wants the
    // accessible name to start with it -- hence the aria-label IR-204 added.
    expect(screen.getByRole("button", { name: "Show password" })).toBeInTheDocument();
  });

  it("reaches a validation error as the field's accessible description", async () => {
    const user = userEvent.setup();
    renderScreen(<LoginPage />, { route: "/login" });

    await user.click(screen.getByRole("button", { name: "Sign In" }));

    // The assertion that matters: not "the text appears somewhere on screen",
    // but "the text is announced *for this field*". A message rendered next to
    // an input it is not associated with reads, to a screen reader user, as an
    // unexplained error on a field they cannot identify.
    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Email Address" })).toHaveAccessibleDescription(
        "Email is required.",
      );
    });

    expect(screen.getByLabelText("Password")).toHaveAccessibleDescription("Password is required.");
  });

  it("marks the invalid fields as invalid, not merely red", async () => {
    const user = userEvent.setup();
    renderScreen(<LoginPage />, { route: "/login" });

    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(screen.getByRole("textbox", { name: "Email Address" })).toBeInvalid();
    });
    expect(screen.getByLabelText("Password")).toBeInvalid();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<LoginPage />, { route: "/login" });

    await expectNoBlockingA11yViolations(container);
  });
});

/**
 * Where a successful sign-in lands (IR-236).
 *
 * The destination is the whole point of the ticket, and it is also the one
 * piece of this screen that takes an instruction from outside the code. Both
 * halves are pinned: it goes where it was asked, and it refuses to be told to
 * go somewhere off-origin.
 */
describe("where the login screen sends you", () => {
  const KTTO_USER = makeUser();

  /**
   * The landing page this role has always had. Read from `roleDashboard.ts`
   * rather than hardcoded, so these tests assert "fell back to the existing
   * default" -- which is the acceptance criterion -- instead of quietly
   * becoming a second, competing definition of where KTTO lands.
   */
  const ROLE_DEFAULT = getRoleDashboardPath(FIXTURE_ROLE);

  function acceptAnyPassword() {
    return vi.spyOn(authApi, "login").mockResolvedValue({
      data: { access: "access-token", refresh: "refresh-token", user: KTTO_USER },
    } as Awaited<ReturnType<typeof authApi.login>>);
  }

  /** Renders the landing page's own path so the test can read where it ended up. */
  function LandedOn() {
    const location = useLocation();
    return <h1>{`landed on ${location.pathname}${location.search}${location.hash}`}</h1>;
  }

  function renderLoginAt(route: string, state?: unknown) {
    return renderScreen(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<LandedOn />} />
      </Routes>,
      { route, state },
    );
  }

  async function signIn() {
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Email Address" }), "ktto@cit.edu");
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
    await user.click(screen.getByRole("button", { name: "Sign In" }));
  }

  afterEach(() => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    });
  });

  it("honours the destination the guard passed it", async () => {
    acceptAnyPassword();
    renderLoginAt("/login", { from: "/review/12/evaluate" });

    await signIn();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "landed on /review/12/evaluate" }),
      ).toBeInTheDocument();
    });
  });

  it("honours a destination that survived a full page load in the query string", async () => {
    // The idle-timeout path is a `window.location` assignment, so router state
    // is gone by the time the login screen mounts. `?next=` is how the
    // destination gets across (`lib/authSession.ts`).
    acceptAnyPassword();
    renderLoginAt("/login?reason=session_expired&next=%2Frecords%2F42");

    await signIn();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "landed on /records/42" })).toBeInTheDocument();
    });
  });

  it("falls back to the role's landing page when no destination was supplied", async () => {
    acceptAnyPassword();
    renderLoginAt("/login");

    await signIn();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: `landed on ${ROLE_DEFAULT}` }),
      ).toBeInTheDocument();
    });
  });

  /**
   * Landing on the role default is necessary evidence but not sufficient: the
   * default is where a visitor with *no* destination goes too, so on its own
   * that assertion would still pass if the whole feature were deleted. The
   * second assertion is the discriminating one -- it says the hostile value was
   * not followed, rather than merely that something else happened.
   */
  async function expectHostileDestinationRefused() {
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: `landed on ${ROLE_DEFAULT}` }),
      ).toBeInTheDocument();
    });
    expect(screen.queryByRole("heading", { name: /evil\.example/ })).not.toBeInTheDocument();
  }

  it("refuses an off-origin destination and uses the default instead", async () => {
    acceptAnyPassword();
    renderLoginAt("/login", { from: "https://evil.example/harvest" });

    await signIn();

    await expectHostileDestinationRefused();
  });

  it("refuses a protocol-relative destination in the query string", async () => {
    acceptAnyPassword();
    renderLoginAt("/login?next=%2F%2Fevil.example%2Fharvest");

    await signIn();

    await expectHostileDestinationRefused();
  });

  it("refuses a destination that assembles itself out of dot segments", async () => {
    // `/..//evil.example` resolves to the pathname `//evil.example`, which is
    // protocol-relative even though the string it arrived as was not.
    acceptAnyPassword();
    renderLoginAt("/login", { from: "/..//evil.example/harvest" });

    await signIn();

    await expectHostileDestinationRefused();
  });

  it("keeps the destination when the session-expired banner is dismissed first", async () => {
    // `dismissSessionAlert` navigates to clear the banner's reason out of
    // router state. Reading the destination at submit time instead of on mount
    // would mean dismissing the banner quietly threw the destination away.
    acceptAnyPassword();
    renderLoginAt("/login", { reason: "session_expired", from: "/review/12/evaluate" });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /dismiss/i }));
    await signIn();

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "landed on /review/12/evaluate" }),
      ).toBeInTheDocument();
    });
  });
});

/**
 * What a failed sign-in says (IR-536, IR-200 defect 2).
 *
 * Before this, any failure without a JSON `detail` -- an nginx 502, a 500, a
 * dropped connection -- fell back to "Invalid email or password", and people
 * re-checked a password that was never wrong. One case per row of IR-536's
 * table, and the "can't be reached" cases are pinned to say nothing about the
 * email or password at all.
 */
describe("what a failed sign-in says", () => {
  /** The shape axios rejects with when the server answered. */
  function serverReplied(status: number, data: unknown) {
    return Object.assign(new Error(`Request failed with status code ${status}`), {
      isAxiosError: true,
      response: { status, data, headers: {} },
    });
  }

  /** The shape axios rejects with when nothing came back: offline, DNS, CORS. */
  function noResponse() {
    return Object.assign(new Error("Network Error"), { isAxiosError: true, request: {} });
  }

  function failSignInWith(...errors: unknown[]) {
    const spy = vi.spyOn(authApi, "login");
    for (const error of errors) spy.mockRejectedValueOnce(error);
    return spy;
  }

  async function signIn(user = userEvent.setup()) {
    await user.type(screen.getByRole("textbox", { name: "Email Address" }), "student@cit.edu");
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
    await user.click(screen.getByRole("button", { name: "Sign In" }));
    return user;
  }

  afterEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("says the credentials did not match on a 401", async () => {
    failSignInWith(serverReplied(401, { detail: "Invalid credentials." }));
    renderScreen(<LoginPage />, { route: "/login" });

    await signIn();

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(screen.getByRole("textbox", { name: "Email Address" })).toBeInvalid();
  });

  it("says the credentials did not match when the server's detail says so", async () => {
    failSignInWith(serverReplied(400, { detail: "Invalid credentials." }));
    renderScreen(<LoginPage />, { route: "/login" });

    await signIn();

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  });

  it("counts down truthfully to the lock", async () => {
    // LOGIN_FAILURE_LIMIT is 3, so the first miss leaves two, not "one more".
    failSignInWith(
      serverReplied(401, { detail: "Invalid credentials." }),
      serverReplied(401, { detail: "Invalid credentials." }),
    );
    renderScreen(<LoginPage />, { route: "/login" });

    const user = await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "2 more failed attempts will lock your account.",
    );

    await user.click(screen.getByRole("button", { name: "Sign In" }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "One more failed attempt will lock your account.",
      );
    });
  });

  it("asks for the email to be verified on a 403 'not verified'", async () => {
    failSignInWith(serverReplied(403, { detail: "Email not verified." }));
    renderScreen(<LoginPage />, { route: "/login" });

    await signIn();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Email not verified");
    expect(alert).not.toHaveTextContent(/password/i);
  });

  it("opens the account-locked dialog on a 403 'locked', as before", async () => {
    failSignInWith(serverReplied(403, { detail: "Account is locked." }));
    renderScreen(<LoginPage />, { route: "/login" });

    await signIn();

    expect(await screen.findByRole("dialog", { name: "Account Locked" })).toBeInTheDocument();
  });

  it("opens the account-locked dialog on django-axes' plain-text 429", async () => {
    // The server-side lock (AXES_FAILURE_LIMIT) answers in text, not JSON, so
    // it has no `detail`. It must still read as a lock, not as an outage --
    // and a fresh tab, with no client-side count, meets it first.
    failSignInWith(
      serverReplied(
        429,
        "Account locked: too many login attempts. Contact an admin to unlock your account.",
      ),
    );
    renderScreen(<LoginPage />, { route: "/login" });

    await signIn();

    expect(await screen.findByRole("dialog", { name: "Account Locked" })).toBeInTheDocument();
  });

  describe.each([
    ["no response at all", noResponse()],
    ["a 502 with an HTML body", serverReplied(502, "<html><body>502 Bad Gateway</body></html>")],
    ["a 500 with a JSON body that has no detail", serverReplied(500, { error: "boom" })],
    ["a 503 that does carry a detail", serverReplied(503, { detail: "Service unavailable." })],
    ["a 404 from the proxy with no JSON detail", serverReplied(404, "Not Found")],
  ])("on %s", (_label, error) => {
    it("says IRIS can't be reached, and nothing about the email or password", async () => {
      failSignInWith(error);
      renderScreen(<LoginPage />, { route: "/login" });

      await signIn();

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("IRIS can't be reached right now");
      expect(alert).not.toHaveTextContent(/email|password|credential/i);
      // The fields were never judged, so they are not marked wrong either.
      expect(screen.getByRole("textbox", { name: "Email Address" })).not.toBeInvalid();
      expect(screen.getByLabelText("Password")).not.toBeInvalid();
    });
  });

  it("never locks the account because the server was down", async () => {
    // The lock counts rejected credentials. An outage rejected nothing.
    failSignInWith(noResponse(), noResponse(), noResponse());
    renderScreen(<LoginPage />, { route: "/login" });

    const user = await signIn();
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Sign In" }));
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledTimes(3);
    });
    expect(screen.queryByRole("dialog", { name: "Account Locked" })).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("IRIS can't be reached right now");
  });

  it("says 'Unable to sign in' with the server's detail for anything else", async () => {
    failSignInWith(
      serverReplied(429, { detail: "Request was throttled. Expected available in 30 seconds." }),
    );
    renderScreen(<LoginPage />, { route: "/login" });

    await signIn();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Unable to sign in");
    expect(alert).toHaveTextContent("Request was throttled. Expected available in 30 seconds.");
  });

  it("has no serious or critical accessibility violations while an error shows", async () => {
    failSignInWith(noResponse());
    const { container } = renderScreen(<LoginPage />, { route: "/login" });

    await signIn();
    await screen.findByRole("alert");

    await expectNoBlockingA11yViolations(container);
  });

  /**
   * Which lock it is, and when it lifts (IR-555). The dialog used to say "try
   * again in 15:00" for every lock. axes lifts after its own cool-off, and
   * RDCO's manual lock never lifts on its own, so the dialog now counts down
   * only to a time the server gave it.
   */
  describe("the locked dialog", () => {
    it("counts down to the server's unlock_at for an axes lockout", async () => {
      const unlockAt = new Date(Date.now() + 90_000).toISOString();
      failSignInWith(
        serverReplied(429, {
          detail: "Account locked: too many failed sign-in attempts.",
          code: "too_many_attempts",
          unlock_at: unlockAt,
        }),
      );
      renderScreen(<LoginPage />, { route: "/login" });

      await signIn();

      const dialog = await screen.findByRole("dialog", { name: "Account Locked" });
      expect(dialog).toHaveTextContent(/try again in 1:(29|30)/i);
    });

    it("names RDCO and shows no countdown for an account RDCO locked", async () => {
      failSignInWith(serverReplied(403, { detail: "Account is locked.", code: "locked_by_admin" }));
      renderScreen(<LoginPage />, { route: "/login" });

      await signIn();

      const dialog = await screen.findByRole("dialog", { name: "Account Locked" });
      expect(dialog).toHaveTextContent(/RDCO/);
      expect(dialog).not.toHaveTextContent(/try again in|\d+:\d\d/i);
    });

    it("shows no countdown for the plain-text 429 an older server sends", async () => {
      failSignInWith(serverReplied(429, "Account locked: too many login attempts."));
      renderScreen(<LoginPage />, { route: "/login" });

      await signIn();

      const dialog = await screen.findByRole("dialog", { name: "Account Locked" });
      expect(dialog).toHaveTextContent(/too many failed sign-in attempts/i);
      expect(dialog).not.toHaveTextContent(/\d+:\d\d/);
    });

    it("keeps the browser's own 15-minute countdown for its own lock", async () => {
      failSignInWith(
        serverReplied(401, { detail: "Invalid credentials." }),
        serverReplied(401, { detail: "Invalid credentials." }),
        serverReplied(401, { detail: "Invalid credentials." }),
      );
      renderScreen(<LoginPage />, { route: "/login" });

      const user = await signIn();
      await screen.findByRole("alert");
      await user.click(screen.getByRole("button", { name: "Sign In" }));
      await screen.findByText(/2 of 3/);
      await user.click(screen.getByRole("button", { name: "Sign In" }));

      const dialog = await screen.findByRole("dialog", { name: "Account Locked" });
      expect(dialog).toHaveTextContent(/try again in (15:00|14:59)/i);
    });

    it.each([
      ["an axes lockout", serverReplied(429, { code: "too_many_attempts", detail: "Locked.", unlock_at: new Date(Date.now() + 60_000).toISOString() })],
      ["an RDCO lock", serverReplied(403, { detail: "Account is locked.", code: "locked_by_admin" })],
    ])("has no serious or critical accessibility violations for %s", async (_label, error) => {
      failSignInWith(error);
      const { container } = renderScreen(<LoginPage />, { route: "/login" });

      await signIn();
      await screen.findByRole("dialog", { name: "Account Locked" });

      await expectNoBlockingA11yViolations(container);
    });
  });
});

/**
 * "Forgot password?" (IR-536). It was a toast-only dead end; IRIS has no
 * self-service reset, so it now says so, in place, and says who resets one.
 */
describe("forgot password", () => {
  afterEach(() => {
    useUIStore.setState({ toasts: [] });
  });

  it("is a disclosure that answers in place, without a toast", async () => {
    const user = userEvent.setup();
    renderScreen(<LoginPage />, { route: "/login" });

    const trigger = screen.getByRole("button", { name: "Forgot password?" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/no self-service password reset/i)).not.toBeInTheDocument();

    trigger.focus();
    await user.keyboard("{Enter}");

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const answer = screen.getByRole("region", { name: "Forgot password?" });
    expect(answer).toHaveTextContent(/no self-service password reset/i);
    expect(answer).toHaveTextContent("RDCO");
    expect(trigger).toHaveAttribute("aria-controls", answer.id);
    expect(useUIStore.getState().toasts).toHaveLength(0);

    await user.keyboard("{Enter}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("has no serious or critical accessibility violations when open", async () => {
    const user = userEvent.setup();
    const { container } = renderScreen(<LoginPage />, { route: "/login" });

    await user.click(screen.getByRole("button", { name: "Forgot password?" }));

    await expectNoBlockingA11yViolations(container);
  });
});
