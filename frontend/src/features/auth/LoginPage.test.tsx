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
