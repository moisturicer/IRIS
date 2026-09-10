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

const LOCKOUT_MS = 15 * 60 * 1000;

type LoginAlert =
  | { kind: "credentials" }
  | { kind: "unverified" }
  | { kind: "generic"; message: string };

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
      navigate(getRoleDashboardPath(res.data.user.role_name), { replace: true });
    } catch (err: unknown) {
      const res = (err as { response?: { status?: number; data?: { detail?: string } } }).response;
      const detail = res?.data?.detail ?? "Invalid email or password.";
      const status = res?.status;
      const detailLower = detail.toLowerCase();

      const locked =
        status === 403 &&
        (detailLower.includes("locked") || detailLower.includes("locked out"));

      if (locked) {
        openLockout(loginId, Date.now() + LOCKOUT_MS);
        setSubmitting(false);
        return;
      }

      if (status === 403 && detailLower.includes("not verified")) {
        setLoginAlert({ kind: "unverified" });
        setSubmitting(false);
        return;
      }

      const attempts = incrementLoginAttempts(loginId);
      setFailedAttempts(attempts);

      if (attempts >= LOGIN_FAILURE_LIMIT) {
        openLockout(loginId, Date.now() + LOCKOUT_MS);
        setSubmitting(false);
        return;
      }

      if (detail === "Invalid credentials." || status === 401) {
        setLoginAlert({ kind: "credentials" });
      } else {
        setLoginAlert({ kind: "generic", message: detail });
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Only a rejected credential says anything about what is *in* the fields.
  // "Unverified" and a generic server failure do not, and marking the fields
  // invalid for those now announces a wrong claim to a screen reader rather
  // than just tinting a border, as it did before IR-204.
  const showFieldError = loginAlert?.kind === "credentials" && !lockoutOpen;

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

      {sessionAlert && (
        <AuthAlert
          variant="session"
          title="Session Expired"
          onDismiss={dismissSessionAlert}
        >
          Your session timed out after 30 minutes of inactivity. Please sign in again.
        </AuthAlert>
      )}

      <h2 className="text-[28px] font-bold text-gray-900">Welcome Back</h2>
      <p className="mt-2 text-[14px] text-gray-500 mb-6">
        Please enter your credentials to access your records.
      </p>

      {loginAlert?.kind === "credentials" && (
        <AuthAlert variant="error" title="Invalid email or password">
          Please check your credentials and try again.
          {failedAttempts > 0 && failedAttempts < LOGIN_FAILURE_LIMIT && (
            <>
              {" "}
              One more failed attempt will lock your account.{" "}
              <strong>Attempt {failedAttempts} of {LOGIN_FAILURE_LIMIT}</strong>
            </>
          )}
        </AuthAlert>
      )}

      {loginAlert?.kind === "unverified" && (
        <AuthAlert variant="warning" title="Email not verified">
          Check your inbox for the verification link, or register again if it expired.
        </AuthAlert>
      )}

      {loginAlert?.kind === "generic" && (
        <AuthAlert variant="error" title="Unable to sign in">
          {loginAlert.message}
        </AuthAlert>
      )}

      <LoginForm
        onSubmit={handleLogin}
        disabled={lockoutOpen}
        showCredentialsError={showFieldError}
        onIdentifierChange={setIdentifier}
      />

      <p className="text-[13px] text-gray-500 text-center mt-5">
        No account?{" "}
        <Link to="/signup" className="text-brand font-semibold hover:underline">
          Sign up
        </Link>
      </p>
    </AuthLayout>
  );
}
