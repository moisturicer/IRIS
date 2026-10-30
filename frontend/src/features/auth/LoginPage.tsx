import { useEffect, useState } from "react";
import type { FormikHelpers } from "formik";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { AccountLockedModal } from "@/components/auth/AccountLockedModal";
import { LoginForm, type LoginFormValues } from "@/components/auth/LoginForm";
import {
  clearLockout,
  getLockoutUntil,
  getLoginAttempts,
  incrementLoginAttempts,
  isAccountLocked,
  LOGIN_FAILURE_LIMIT,
  resetLoginAttempts,
  setLockoutUntil,
} from "@/lib/authSession";
import { getRoleDashboardPath } from "@/lib/roleDashboard";
import { safeRedirectPath } from "@/lib/redirectTarget";
import { classifyLoginFailure, type LoginFailure } from "./loginFailure";

const LOCKOUT_MS = 15 * 60 * 1000;

/** Every failure but a lock, which opens its own dialog instead. */
type LoginAlert = Exclude<LoginFailure, { kind: "locked" }>;

export default function LoginPage() {
  const navigate       = useNavigate();
  const location       = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { login }      = useAuth();
  const [loginAlert, setLoginAlert]     = useState<LoginAlert | null>(null);
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [lockoutOpen, setLockoutOpen]   = useState(false);
  const [lockoutUntil, setLockoutUntilState] = useState<number | undefined>();
  const [lockoutIdentifier, setLockoutIdentifier] = useState("");
  const [identifier, setIdentifier] = useState("");
  /**
   * The page this visitor asked for before they were sent here, or `null` to
   * use the role's normal landing page (IR-236).
   *
   * **Captured once, on mount, on purpose.** The guard passes it in router
   * state, and `dismissSessionAlert` below navigates to clear that state — so
   * reading it at submit time would mean a visitor who dismisses the
   * "session expired" banner before signing in silently loses their
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
  // IR-642: Settings sends a person here after changing their password,
  // which ends every session. Read once, like `redirectTo`.
  const [passwordChanged] = useState(
    () => (location.state as { reason?: string } | null)?.reason === "password_changed",
  );
  const sessionExpiredFromState =
    (location.state as { reason?: string } | null)?.reason === "session_expired";
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
      setLockoutUntilState(until);
      setLockoutOpen(true);
    }
    setFailedAttempts(getLoginAttempts(identifier));
  }, [identifier]);

  const dismissSessionAlert = () => {
    setSessionAlert(false);
    if (searchParams.get("reason")) {
      searchParams.delete("reason");
      setSearchParams(searchParams, { replace: true });
    }
    if ((location.state as { reason?: string } | null)?.reason === "session_expired") {
      // Clearing the state wholesale is safe: `redirectTo` was captured on
      // mount, so the destination does not live here any more. Writing it back
      // would only look like it mattered.
      navigate("/login", { replace: true, state: null });
    }
  };

  const openLockout = (forIdentifier: string, untilMs: number) => {
    setLockoutUntil(forIdentifier, untilMs);
    setLockoutIdentifier(forIdentifier);
    setLockoutUntilState(untilMs);
    setLockoutOpen(true);
    setLoginAlert(null);
  };

  const closeLockout = () => {
    setLockoutOpen(false);
    if (lockoutIdentifier && lockoutUntil && lockoutUntil <= Date.now()) {
      clearLockout(lockoutIdentifier);
    }
  };

  const handleLogin = async (
    data: LoginFormValues,
    { setSubmitting }: FormikHelpers<LoginFormValues>
  ) => {
    setLoginAlert(null);

    const loginId = data.identifier.trim();

    if (isAccountLocked(loginId)) {
      openLockout(loginId, getLockoutUntil(loginId)!);
      setSubmitting(false);
      return;
    }

    try {
      const res = await authApi.login({ email: loginId, password: data.password });
      resetLoginAttempts(loginId);
      clearLockout(loginId);
      login(res.data.user, res.data.access, res.data.refresh);
      // Back to the page they asked for, or -- when they simply came to sign
      // in, or asked for somewhere `safeRedirectPath` refused -- the landing
      // page their role has always had.
      navigate(redirectTo ?? getRoleDashboardPath(res.data.user.role_name), { replace: true });
    } catch (err: unknown) {
      const failure = classifyLoginFailure(err);

      if (failure.kind === "locked") {
        openLockout(loginId, Date.now() + LOCKOUT_MS);
        return;
      }

      // Neither of these judged the password, so neither counts towards the
      // lock: an unverified account is not a wrong guess, and a server that
      // could not be reached rejected nothing (IR-536).
      if (failure.kind === "unverified" || failure.kind === "unreachable") {
        setLoginAlert(failure);
        return;
      }

      const attempts = incrementLoginAttempts(loginId);
      setFailedAttempts(attempts);

      if (attempts >= LOGIN_FAILURE_LIMIT) {
        openLockout(loginId, Date.now() + LOCKOUT_MS);
        return;
      }

      setLoginAlert(failure);
    } finally {
      setSubmitting(false);
    }
  };

  // Only a rejected credential says anything about what is *in* the fields.
  // "Unverified" and a generic server failure do not, and marking the fields
  // invalid for those now announces a wrong claim to a screen reader rather
  // than just tinting a border, as it did before IR-204.
  const showFieldError = loginAlert?.kind === "credentials" && !lockoutOpen;
  const attemptsLeft = LOGIN_FAILURE_LIMIT - failedAttempts;

  return (
    <AuthLayout
      variant="login"
      before={
        <AccountLockedModal
          open={lockoutOpen}
          onClose={closeLockout}
          unlockAt={lockoutUntil}
        />
      }
    >

      {passwordChanged && (
        <AuthAlert variant="warning" title="Password changed">
          You were signed out on every device. Sign in again with your new password.
        </AuthAlert>
      )}

      {sessionAlert && (
        <AuthAlert
          variant="session"
          title="Session Expired"
          onDismiss={dismissSessionAlert}
        >
          Your session timed out after 30 minutes of inactivity. Please sign in again.
        </AuthAlert>
      )}

      <h2 className="text-balance font-display text-display font-semibold text-stone-900">Welcome Back</h2>
      <p className="mt-2 mb-section text-body text-stone-600">
        Please enter your credentials to access your records.
      </p>

      {loginAlert?.kind === "credentials" && (
        <AuthAlert variant="error" title="Invalid email or password">
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
        </AuthAlert>
      )}

      {/* Says nothing about the fields on purpose: the server never judged
          them, and a credentials message here is what IR-200 reported. */}
      {loginAlert?.kind === "unreachable" && (
        <AuthAlert variant="error" title="IRIS can't be reached right now">
          This is a connection or server problem, not a problem with what you typed.
          Try again shortly.
        </AuthAlert>
      )}

      {loginAlert?.kind === "unverified" && (
        <AuthAlert variant="warning" title="Email not verified">
          Check your inbox for the verification link, or register again if it expired.
        </AuthAlert>
      )}

      {loginAlert?.kind === "other" && (
        <AuthAlert variant="error" title="Unable to sign in">
          {loginAlert.detail}
        </AuthAlert>
      )}

      <LoginForm
        onSubmit={handleLogin}
        disabled={lockoutOpen}
        showCredentialsError={showFieldError}
        onIdentifierChange={setIdentifier}
      />

      <p className="mt-5 text-center text-sm text-stone-600">
        No account?{" "}
        <Link to="/signup" className="text-brand font-semibold hover:underline">
          Sign up
        </Link>
      </p>
    </AuthLayout>
  );
}
