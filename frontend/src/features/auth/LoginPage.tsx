import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useNoticeStore } from "@/store/notice.store";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { EntryErrorDialog, type EntryError } from "@/components/auth/EntryErrorDialog";
import { EntryFrame, EntryTab } from "@/components/auth/EntryFrame";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { AccountLockedModal } from "@/components/auth/AccountLockedModal";
import { SessionNoticeDialog } from "@/components/auth/SessionNoticeDialog";
import { LoginForm, type LoginFormValues } from "@/components/auth/LoginForm";
import {
  clearLockout,
  getLockoutUntil,
  getLoginAttempts,
  incrementLoginAttempts,
  isAccountLocked,
  LOGIN_FAILURE_LIMIT,
  resetLoginAttempts,
  sessionEndMessage,
  setLockoutUntil,
} from "@/lib/authSession";
import { canOpenPath } from "@/lib/access";
import type { User } from "@/types/auth";
import { landingPathFor } from "@/lib/landing";
import { safeRedirectPath } from "@/lib/redirectTarget";
import { sessionAccount } from "@/lib/authSession";
import { preloadScreen, preloadWhenIdle } from "@/router/lazyScreens";
import { classifyLoginFailure, type AccountLock, type LoginFailure } from "./loginFailure";

/**
 * How long the browser's own lock lasts, after `LOGIN_FAILURE_LIMIT` rejected
 * credentials in this tab (NFR-S6). It is this lock's only: a server lock's
 * time comes from the server, and replaces this one when both apply (IR-555).
 */
const CLIENT_LOCKOUT_MS = 15 * 60 * 1000;

/** Every failure but a lock, which opens its own dialog instead. */
type LoginAlert = Exclude<LoginFailure, { kind: "locked" }>;

/**
 * May this account be sent back to the page saved before sign-in (IR-1207)?
 * Often the saved page belongs to the account that signed out before them.
 * Django staff with no IRIS role pass every route guard (`ProtectedRoute`), so
 * they may return anywhere; everyone else only where their role may go.
 */
function mayReturnTo(user: User, path: string): boolean {
  if ((user.is_staff || user.is_superuser) && !user.role_name) return true;
  return canOpenPath(user.role_name, path);
}

export default function LoginPage() {
  // The submitting button may lose focus when the form disables it, before the
  // lock reply arrives. Keep its actual element as the dialog's return target.
  const signInRef = useRef<HTMLButtonElement>(null);
  // Where a failure's dialog returns focus: the field most often retyped.
  const passwordRef = useRef<HTMLInputElement>(null);
  const navigate       = useNavigate();
  const location       = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { login, user: signedInUser, isAuthenticated } = useAuth();
  /**
   * Set while this screen's own sign-in is completing, so the signed-in
   * redirect below does not race `handleLogin`'s own navigation (IR-1215).
   */
  const signingIn = useRef(false);
  const [loginAlert, setLoginAlert]     = useState<LoginAlert | null>(null);
  // The failure stays after its dialog closes, so the fields stay marked wrong
  // until the next attempt; only the dialog goes (IR-1303).
  const [alertOpen, setAlertOpen]       = useState(false);
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [lockoutOpen, setLockoutOpen]   = useState(false);
  const [lock, setLock]                 = useState<AccountLock | null>(null);
  const [lockoutIdentifier, setLockoutIdentifier] = useState("");
  const [identifier, setIdentifier] = useState("");
  /**
   * The page this visitor asked for before they were sent here, or `null` to
   * use the normal landing page (IR-236, IR-534).
   *
   * **Captured once, on mount, on purpose.** The guard passes it in router
   * state, and `dismissSignedOutNotice` below navigates to clear that state — so
   * reading it at submit time would mean a visitor who dismisses the
   * "session expired" dialog before signing in silently loses their
   * destination. It is also validated once here rather than at the point of
   * navigation, so there is no path from an unchecked string to `navigate`.
   *
   * `?next=` is read as well as router state because the idle-timeout path in
   * `lib/authSession.ts` reaches the login screen through a full page load,
   * which no in-memory state survives.
   */
  const [redirectTo] = useState<string | null>(() => {
    const fromState = (location.state as { from?: unknown } | null)?.from;
    return safeRedirectPath(fromState) ?? safeRedirectPath(searchParams.get("next"));
  });
  /**
   * The account whose session this tab last held, read once on mount for the
   * same reason as `redirectTo`: signing in records the new one (IR-1242).
   */
  const [previousAccount] = useState<number | null>(() => sessionAccount());
  /**
   * Where a signed-in person goes from here: the saved page when it was their
   * own session that ended on it and their role may open it, else their
   * landing page (IR-1207, IR-1242).
   *
   * A saved page on a shared device is often the last account's, and that is
   * not this person's to land on even when their role may open it. With no
   * account on record (a fresh tab, a link opened while signed out) the page is
   * the one this visitor asked for, and is followed. A page typed while signed
   * in still meets the guard's "not for you" screen; only this return trip
   * skips it.
   */
  const isPreviousAccount = (user: User) => previousAccount === null || previousAccount === user.id;
  const destinationFor = (user: User) =>
    redirectTo && isPreviousAccount(user) && mayReturnTo(user, redirectTo)
      ? redirectTo
      : landingPathFor(user);
  // IR-642: Settings sends a person here after changing their password,
  // which ends every session. Read once, like `redirectTo`.
  const [passwordChanged, setPasswordChanged] = useState(
    () => (location.state as { reason?: string } | null)?.reason === "password_changed",
  );
  const sessionExpiredFromState =
    (location.state as { reason?: string } | null)?.reason === "session_expired";
  // Why the server ended the session (IR-645); inactivity when it did not say.
  // The address carries it across a full page load; router state carries it
  // from the route guard (IR-1081).
  const sessionEnd = sessionEndMessage(
    searchParams.get("code") ?? (location.state as { code?: unknown } | null)?.code,
  );
  const [sessionAlert, setSessionAlert] = useState(
    () => searchParams.get("reason") === "session_expired" || sessionExpiredFromState
  );

  useEffect(() => {
    if (
      searchParams.get("reason") === "session_expired" ||
      (location.state as { reason?: string } | null)?.reason === "session_expired"
    ) {
      setSessionAlert(true);
    }
  }, [searchParams, location.state]);

  useEffect(() => {
    if (!identifier) return;
    const until = getLockoutUntil(identifier);
    if (until) {
      setLockoutIdentifier(identifier);
      setLock({ by: "attempts", unlockAt: until });
      setLockoutOpen(true);
    }
    setFailedAttempts(getLoginAttempts(identifier));
  }, [identifier]);

  // Sign-up and password reset load on demand (IR-1248). Fetch them while the
  // reader is still on Sign in, so the link finds them here (IR-1262).
  useEffect(() => preloadWhenIdle(["/signup", "/password/forgot"]), []);

  // Why they were signed out, as a dialog in front of the page (IR-1197).
  const signedOutNotice = passwordChanged
    ? {
        title: "Password Changed",
        text: "You were signed out on every device. Sign in again with your new password.",
      }
    : sessionAlert
      ? sessionEnd
      : null;

  const dismissSignedOutNotice = () => {
    setPasswordChanged(false);
    setSessionAlert(false);
    if (searchParams.get("reason") || searchParams.get("code")) {
      searchParams.delete("reason");
      searchParams.delete("code");
      setSearchParams(searchParams, { replace: true });
    }
    const reason = (location.state as { reason?: string } | null)?.reason;
    if (reason === "session_expired" || reason === "password_changed") {
      // Clearing the state wholesale is safe: `redirectTo` was captured on
      // mount, so the destination does not live here any more. Writing it back
      // would only look like it mattered. Cleared, a reload shows no notice.
      navigate("/login", { replace: true, state: null });
    }
    // Nothing opened the dialog, so its focus has nowhere to return: start
    // them on the form they came to fill in.
    globalThis.setTimeout(() => document.getElementById("login-identifier")?.focus());
  };

  const openLockout = (forIdentifier: string, next: AccountLock) => {
    // Only a lock with a known end is remembered, so the dialog can reopen on
    // it in this tab; RDCO's lock and a lock with no time are asked of the
    // server again on the next attempt.
    if (next.by === "attempts" && next.unlockAt !== null) {
      setLockoutUntil(forIdentifier, next.unlockAt);
    }
    setLockoutIdentifier(forIdentifier);
    setLock(next);
    setLockoutOpen(true);
    setLoginAlert(null);
  };

  const closeLockout = () => {
    setLockoutOpen(false);
    if (
      lockoutIdentifier && lock?.by === "attempts" && lock.unlockAt !== null &&
      lock.unlockAt <= Date.now()
    ) {
      clearLockout(lockoutIdentifier);
    }
  };

  const showAlert = (failure: LoginAlert) => {
    setLoginAlert(failure);
    setAlertOpen(true);
  };

  const handleLogin = async (data: LoginFormValues) => {
    setLoginAlert(null);

    const loginId = data.identifier.trim();

    if (isAccountLocked(loginId)) {
      openLockout(loginId, { by: "attempts", unlockAt: getLockoutUntil(loginId)! });
      return;
    }

    try {
      const res = await authApi.login({ email: loginId, password: data.password, remember: data.remember });
      resetLoginAttempts(loginId);
      clearLockout(loginId);
      signingIn.current = true;
      login(res.data.user, res.data.access, res.data.remembered === true);
      // Every other request is refused until they answer, so the guard shows
      // the notice before the page loads (IR-790).
      if (res.data.notice_answer_required) useNoticeStore.getState().require();
      // Back to the page they asked for, or -- when they simply came to sign
      // in, or asked for somewhere `safeRedirectPath` or their role refused --
      // My Reviews when they have review work, otherwise Discover (IR-534).
      navigate(destinationFor(res.data.user), { replace: true });
    } catch (err: unknown) {
      const failure = classifyLoginFailure(err);

      if (failure.kind === "locked") {
        openLockout(loginId, failure.lock);
        return;
      }

      // None of these judged the password, so none counts towards the lock: an
      // unverified account is not a wrong guess, a server that could not be
      // reached rejected nothing (IR-536), and a rate limit counts the address
      // a whole campus may share (IR-661).
      if (failure.kind === "unverified" || failure.kind === "unreachable" || failure.kind === "throttled") {
        showAlert(failure);
        return;
      }

      const attempts = incrementLoginAttempts(loginId);
      setFailedAttempts(attempts);

      if (attempts >= LOGIN_FAILURE_LIMIT) {
        openLockout(loginId, { by: "attempts", unlockAt: Date.now() + CLIENT_LOCKOUT_MS });
        return;
      }

      showAlert(failure);
    }
  };

  // Only a rejected credential says anything about what is *in* the fields.
  // "Unverified" and a generic server failure do not, and marking the fields
  // invalid for those now announces a wrong claim to a screen reader rather
  // than just tinting a border, as it did before IR-204.
  const showFieldError = loginAlert?.kind === "credentials" && !lockoutOpen;
  const attemptsLeft = LOGIN_FAILURE_LIMIT - failedAttempts;

  /** What each failure says, in the dialog in front of the form (IR-1303). */
  const alertContent = (alert: LoginAlert): EntryError => {
    switch (alert.kind) {
      case "credentials":
        return {
          title: "Invalid email or password",
          body: (
            <>
              Please check your credentials and try again.
              {attemptsLeft > 0 && attemptsLeft < LOGIN_FAILURE_LIMIT && (
                <>
                  {" "}
                  {attemptsLeft === 1
                    ? "One more failed attempt will lock your account."
                    : `${attemptsLeft} more failed attempts will lock your account.`}{" "}
                  <strong>Attempt {failedAttempts} of {LOGIN_FAILURE_LIMIT}</strong>
                </>
              )}
            </>
          ),
        };
      // Says nothing about the fields on purpose: the server never judged
      // them, and a credentials message here is what IR-200 reported.
      case "unreachable":
        return {
          title: "IRIS can't be reached right now",
          body: "This is a connection or server problem, not a problem with what you typed. Try again shortly.",
        };
      case "unverified":
        return {
          title: "Email not verified",
          body: (
            <>
              Check your inbox for the verification link. If it expired or never arrived,{" "}
              {/* The typed address rides in router state, never the URL (IR-643). */}
              <Link to="/verify-email/resend" state={{ email: identifier }} className="font-semibold text-brand underline">
                resend verification email
              </Link>
              .
            </>
          ),
        };
      case "throttled":
        return { title: "Unable to sign in", body: alert.message };
      case "other":
        return { title: "Unable to sign in", body: alert.detail };
    }
  };

  // Someone whose session is still valid has nothing to do here (IR-1215).
  // `AuthBootstrap` renders no page until the session is restored, so this
  // reads the settled answer, never the moment before a refresh completes.
  if (isAuthenticated && signedInUser && !signingIn.current) {
    return <Navigate to={destinationFor(signedInUser)} replace />;
  }

  return (
    <EntryFrame
      help
      lede={{
        headline: <>Your research has <span className="text-brand">a place.</span></>,
        sentence:
          "IRIS brings research submission, review, approval, and discovery into one connected workspace. From initial submission to institutional clearance and publication, every step has its place.",
      }}
      tabs={<EntryTab>Sign in</EntryTab>}
      before={
        <>
          <SessionNoticeDialog notice={signedOutNotice} onClose={dismissSignedOutNotice} />
          <EntryErrorDialog
            error={alertOpen && loginAlert ? alertContent(loginAlert) : null}
            onClose={() => setAlertOpen(false)}
            returnTo={passwordRef.current}
          />
          <AccountLockedModal
            open={lockoutOpen}
            onClose={closeLockout}
            lock={lock}
            returnTo={signInRef.current}
          />
        </>
      }
    >

      <h2 className="text-balance font-display text-display font-semibold text-stone-900">Welcome back</h2>
      <p className="mt-2 mb-section text-body text-stone-600">
        Sign in to access your research workspace.
      </p>

      <LoginForm
        submitRef={signInRef}
        passwordRef={passwordRef}
        onSubmit={handleLogin}
        disabled={lockoutOpen}
        showCredentialsError={showFieldError}
        onIdentifierChange={setIdentifier}
      />

      <p className="mt-5 text-center text-sm text-stone-600">
        New to IRIS?{" "}
        <Link
          to="/signup"
          onMouseEnter={() => void preloadScreen("/signup")}
          onFocus={() => void preloadScreen("/signup")}
          className={cn(
            "inline-flex min-h-11 min-w-11 items-center justify-center rounded-control text-brand font-semibold hover:underline",
            FOCUS_RING,
          )}
        >
          Create an account
        </Link>
      </p>
    </EntryFrame>
  );
}
