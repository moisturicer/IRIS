/**
 * The route guard's four states, asserted through what a visitor actually sees
 * (IR-236).
 *
 * The guard decides one thing — does this request reach the route, wait, get
 * sent to sign in, or get refused — and each answer has a different failure
 * cost. Sending a signed-in user to the login screen loses their work; refusing
 * a permitted one looks like a bug; redirecting *before hydration finishes*
 * signs everyone out on a cold boot, which is the defect the parent spec
 * (IR-234) exists to close. So all four are pinned here rather than the one
 * this ticket changed.
 *
 * **Queries go through the accessible tree.** The destination the guard hands
 * to the login screen is not something a visitor sees, so the login stub below
 * renders it as a heading — role plus accessible name, the same pair a screen
 * reader would announce — rather than being read out of router internals.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { Route, Routes, useLocation } from "react-router-dom";

import { useAuthStore } from "@/store/auth.store";
import { ROLES } from "@/lib/constants";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { expiredToken, makeUser, validToken } from "@/test/authFixtures";
import { renderScreen, screen } from "@/test/render";

import { ProtectedRoute } from "./ProtectedRoute";

/**
 * Stands in for the login screen so the test can see what the guard sent it.
 *
 * The two values are real headings with real text. An earlier version hung
 * them on `aria-label` on a bare `<p>`, which ARIA prohibits on a role-less
 * element and screen readers do not reliably announce — a test asserting on
 * that would have been checking something no user could perceive.
 */
function LoginStub() {
  const location = useLocation();
  const state = (location.state ?? {}) as { from?: string; reason?: string };
  return (
    <div>
      <h1>Sign in</h1>
      <h2>{`destination ${state.from ?? "none"}`}</h2>
      <h2>{`reason ${state.reason ?? "none"}`}</h2>
    </div>
  );
}

function renderGuardAt(route: string) {
  return renderScreen(
    <Routes>
      <Route path="/login" element={<LoginStub />} />
      <Route element={<ProtectedRoute allowedRoles={[ROLES.KTTO]} />}>
        <Route path="/review/:id/evaluate" element={<h1>Evaluate</h1>} />
        <Route path="/review" element={<h1>Review queue</h1>} />
      </Route>
    </Routes>,
    { route },
  );
}

/** The store is a module-level singleton, so each test starts from a clean one. */
beforeEach(() => {
  useAuthStore.setState({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    authReady: false,
  });
});

describe("the route guard", () => {
  it("waits while hydration is still running, and does not redirect", () => {
    // The cold-boot case. The refresh token lives in sessionStorage and is read
    // asynchronously, so for the first moments of a page load there is no
    // access token *and* no evidence there is no session. Treating that as
    // "signed out" is what bounced a reviewer with a perfectly good session to
    // the login screen.
    useAuthStore.setState({ authReady: false, accessToken: null });

    renderGuardAt("/review/12/evaluate");

    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Evaluate" })).not.toBeInTheDocument();

    // Found by role, then asserted on its *contents* rather than its name --
    // and the distinction is the whole point. ARIA does not compute a `status`
    // region's name from its content, so a live region can have a perfectly
    // good `aria-label` and still announce nothing, because what assistive
    // technology reads out when the region changes is the text inside it. The
    // spinner is `aria-hidden`, so this span is the only announceable thing
    // here; if it went back to being empty this assertion is what would fail.
    const waiting = screen.getByRole("status");
    expect(waiting).toHaveTextContent("Loading…");
    expect(waiting).toHaveAttribute("aria-live", "polite");
  });

  it("sends a visitor with no session to sign in, carrying the page they asked for", () => {
    useAuthStore.setState({ authReady: true, accessToken: null });

    renderGuardAt("/review/12/evaluate");

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "destination /review/12/evaluate" })).toBeInTheDocument();
  });

  it("carries the query string and fragment of the page they asked for", () => {
    useAuthStore.setState({ authReady: true, accessToken: null });

    renderGuardAt("/review?status=pending#row-3");

    expect(screen.getByRole("heading", { name: "destination /review?status=pending#row-3" })).toBeInTheDocument();
  });

  it("keeps its own reason when the session expired, and still carries the destination", () => {
    // An expired session and an absent one are different events to the person
    // in front of the screen: one of them deserves "you were signed out", the
    // other deserves silence. The destination rides along with both.
    useAuthStore.setState({
      authReady: true,
      accessToken: expiredToken(),
      user: makeUser(),
      isAuthenticated: true,
    });

    renderGuardAt("/review/12/evaluate");

    expect(screen.getByRole("heading", { name: "reason session_expired" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "destination /review/12/evaluate" })).toBeInTheDocument();
  });

  it("says nothing about a reason when there was simply no session", () => {
    useAuthStore.setState({ authReady: true, accessToken: null });

    renderGuardAt("/review/12/evaluate");

    expect(screen.getByRole("heading", { name: "reason none" })).toBeInTheDocument();
  });

  it("renders the route for a valid token with a permitted role", () => {
    useAuthStore.setState({
      authReady: true,
      accessToken: validToken(),
      user: makeUser(),
      isAuthenticated: true,
    });

    renderGuardAt("/review/12/evaluate");

    expect(screen.getByRole("heading", { name: "Evaluate" })).toBeInTheDocument();
  });

  it("refuses a signed-in user who lacks the role, rather than bouncing them to sign in", () => {
    // The distinction this pins: being refused is not being signed out. A
    // student who follows a colleague's link to the review queue is told they
    // may not open it — sending them to the login screen would invite them to
    // sign in again as if their session were the problem.
    useAuthStore.setState({
      authReady: true,
      accessToken: validToken({ user_id: 9, role_id: 1 }),
      user: makeUser({ id: 9, role: 1, role_name: ROLES.STUDENT }),
      isAuthenticated: true,
    });

    renderGuardAt("/review/12/evaluate");

    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /access denied/i })).toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations while waiting", async () => {
    useAuthStore.setState({ authReady: false, accessToken: null });

    const { container } = renderGuardAt("/review/12/evaluate");

    await expectNoBlockingA11yViolations(container);
  });

  it("has no serious or critical accessibility violations when it refuses", async () => {
    // The other state this guard renders itself. The redirect states are not
    // scanned: what they render is the login screen, which has its own suite --
    // scanning the stub here would only be testing the stub.
    useAuthStore.setState({
      authReady: true,
      accessToken: validToken({ user_id: 9, role_id: 1 }),
      user: makeUser({ id: 9, role: 1, role_name: ROLES.STUDENT }),
      isAuthenticated: true,
    });

    const { container } = renderGuardAt("/review/12/evaluate");

    await expectNoBlockingA11yViolations(container);
  });
});
