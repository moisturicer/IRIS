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
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

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
 * The Dossier frame (IR-706; IR-704 stories 1-5, 12, 58).
 *
 * The masthead is the page's one visible `<h1>`, and both logos are inside it,
 * so its accessible name says whose system this is.
 */
describe("the frame sign in opens in", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("names IRIS and CIT-U in the masthead, the page's only top-level heading", () => {
    renderScreen(<LoginPage />, { route: "/login" });

    const [masthead, ...others] = screen.getAllByRole("heading", { level: 1 });
    expect(others).toEqual([]);
    expect(masthead).toHaveAccessibleName(/IRIS/);
    expect(masthead).toHaveAccessibleName(/Cebu Institute of Technology/);
    expect(screen.getByRole("heading", { level: 2, name: "Welcome Back" })).toBeInTheDocument();
  });

  it("offers Register in the masthead and under the form, and no longer says 'Sign up'", () => {
    renderScreen(<LoginPage />, { route: "/login" });

    const links = screen.getAllByRole("link", { name: "Register" });
    expect(links).toHaveLength(2);
    links.forEach((link) => expect(link).toHaveAttribute("href", "/signup"));
    expect(screen.queryByRole("link", { name: /sign up/i })).not.toBeInTheDocument();
  });

  it("labels the sheet with one Sign in tab that is not a control", () => {
    renderScreen(<LoginPage />, { route: "/login" });

    expect(screen.getByText("Sign in")).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("says what IRIS is in one plain sentence under the headline", () => {
    renderScreen(<LoginPage />, { route: "/login" });

    expect(screen.getByText(/Your research has/)).toHaveTextContent("Your research has a place.");
    expect(screen.getByText(/^IRIS is CIT-U's system for submitting/)).toBeInTheDocument();
  });

  it("carries CIT-U's name in the footer and no policy link until IR-214", () => {
    renderScreen(<LoginPage />, { route: "/login" });

    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent("Cebu Institute of Technology – University");
    expect(within(footer).queryAllByRole("link")).toEqual([]);
  });

  it("announces a failed sign-in once, by the banner, and only marks the fields", async () => {
    vi.spyOn(authApi, "login").mockRejectedValueOnce(
      Object.assign(new Error("Request failed with status code 401"), {
        isAxiosError: true,
        response: { status: 401, data: { detail: "Invalid credentials." }, headers: {} },
      }),
    );
    const user = userEvent.setup();
    const { container } = renderScreen(<LoginPage />, { route: "/login" });

    await user.type(screen.getByRole("textbox", { name: "Email Address" }), "student@cit.edu");
    await user.type(screen.getByLabelText("Password"), "IrisDemo123!");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    // One live region in the whole page: the banner. The fields say nothing.
    // `aria-live` has no role to query by, so the live-region semantics are
    // read as attributes -- still the accessible tree, never a class or test id.
    expect(container.ownerDocument.querySelectorAll('[role="alert"], [role="status"], [aria-live]')).toHaveLength(1);
    const email = screen.getByRole("textbox", { name: "Email Address" });
    expect(email).toBeInvalid();
    expect(email).not.toHaveAccessibleDescription();
    expect(screen.getByLabelText("Password")).toBeInvalid();
    expect(screen.getByLabelText("Password")).not.toHaveAccessibleDescription();
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
    it("moves focus inside, traps Tab, and returns focus when Escape closes it", async () => {
      // jsdom has no layout; report a visible rect for the browser focus trap.
      vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([{}] as unknown as DOMRectList);
      failSignInWith(serverReplied(403, { detail: "Account is locked.", code: "locked_by_admin" }));
      renderScreen(<LoginPage />, { route: "/login" });
      const user = await signIn();
      await screen.findByRole("dialog", { name: "Account Locked" });

      const close = screen.getByRole("button", { name: "Close" });
      expect(close).toHaveFocus();
      await user.tab();
      expect(close).toHaveFocus();
      await user.tab({ shift: true });
      expect(close).toHaveFocus();
      await user.keyboard("{Escape}");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Sign In" })).toHaveFocus();
    });

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
 * "Forgot password?" (IR-536, then IR-642). IR-536 replaced a toast-only dead
 * end with a disclosure naming RDCO, because there was no self-service reset.
 * ADR-045 adds one, so the control is now a link to it; RDCO stays in the
 * recovery email and the confirmation as support guidance.
 */
describe("forgot password", () => {
  afterEach(() => {
    useUIStore.setState({ toasts: [] });
  });

  it("is a link to the self-service reset, reachable by keyboard", async () => {
    const user = userEvent.setup();
    renderScreen(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/password/forgot" element={<p>forgot screen</p>} />
      </Routes>,
      { route: "/login" },
    );

    const link = screen.getByRole("link", { name: "Forgot password?" });
    expect(link).toHaveAttribute("href", "/password/forgot");
    expect(screen.queryByText(/no self-service password reset/i)).not.toBeInTheDocument();

    link.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByText("forgot screen")).toBeInTheDocument();
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<LoginPage />, { route: "/login" });
    await expectNoBlockingA11yViolations(container);
  });
});

/**
 * Why the session ended (IR-645).
 *
 * The server's refusal names a reason (`code`), and `lib/authSession.ts`
 * carries it across the full page load as `?code=`. Each reason has its own
 * message: someone who signed out in another tab must not be told they were
 * away too long. A missing or unknown code keeps the inactivity message, which
 * is what every sign-out said before.
 */
describe("why the session ended", () => {
  const cases = [
    { code: "session_idle", title: "Session Expired", text: /30 minutes of inactivity/ },
    { code: "session_ended", title: "Signed Out", text: /signed out of this session/ },
    { code: "account_locked", title: "Account Locked", text: /your account was locked/ },
    {
      code: "session_ended_password_changed",
      title: "Password Changed",
      text: /your password was changed on another device/,
    },
    { code: "session_ended_revoked", title: "Session Ended", text: /An administrator ended this session/ },
  ];

  it.each(cases)("says why for $code", async ({ code, title, text }) => {
    const { container } = renderScreen(<LoginPage />, {
      route: `/login?reason=session_expired&code=${code}`,
    });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(title);
    expect(alert).toHaveTextContent(text);
    await expectNoBlockingA11yViolations(container);
  });

  it("gives every code a message of its own", () => {
    const shown = cases.map(({ code }) => {
      const { unmount } = renderScreen(<LoginPage />, {
        route: `/login?reason=session_expired&code=${code}`,
      });
      const text = screen.getByRole("alert").textContent;
      unmount();
      return text;
    });
    expect(new Set(shown).size).toBe(cases.length);
  });

  it.each([
    { label: "no code", route: "/login?reason=session_expired" },
    { label: "an unknown code", route: "/login?reason=session_expired&code=token_not_valid" },
  ])("keeps the inactivity message for $label", ({ route }) => {
    renderScreen(<LoginPage />, { route });

    expect(screen.getByRole("alert")).toHaveTextContent(/30 minutes of inactivity/);
  });

  it("clears the reason from the address when dismissed", async () => {
    const user = userEvent.setup();
    renderScreen(<LoginPage />, { route: "/login?reason=session_expired&code=session_ended" });

    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
