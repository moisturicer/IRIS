import { useEffect, useState } from "react";
import type { FormikHelpers } from "formik";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { AuthAlert } from "@/components/auth/AuthAlert";
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
import irisLogo from "@/assets/images/iris_logo.png";

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

  const showFieldError = loginAlert !== null && !lockoutOpen;

  return (
    <div className="min-h-screen flex flex-col lg:flex-row font-sans relative">

      <AccountLockedModal
        open={lockoutOpen}
        onClose={closeLockout}
        unlockAt={lockoutUntil}
      />

      <div className="relative lg:w-1/2 bg-cream flex flex-col justify-between overflow-hidden px-8 py-10 sm:px-12 lg:px-14 lg:py-12 min-h-[320px] lg:min-h-screen">

        <div className="absolute rounded-full bg-white/60 pointer-events-none"
             style={{ width: 280, height: 280, top: -60, right: -40 }} />
        <div className="absolute rounded-full bg-white/40 pointer-events-none"
             style={{ width: 200, height: 200, bottom: 120, left: -50 }} />
        <div className="absolute rounded-full bg-white/50 pointer-events-none"
             style={{ width: 140, height: 140, bottom: 280, right: 60 }} />

        <div className="relative z-10">
          <img src={irisLogo} alt="IRIS" className="h-14 w-14 object-contain" />

          <p className="mt-5 text-[11px] font-semibold tracking-[0.12em] text-gold uppercase leading-snug max-w-[280px]">
            Cebu Institute of Technology – University
          </p>

          <h1 className="mt-4 text-[56px] sm:text-[64px] font-extrabold text-brand leading-none tracking-tight">
            IRIS
          </h1>

          <p className="mt-3 text-[15px] font-medium text-gray-700">
            Intelligent Research &amp; IP System
          </p>
          <p className="mt-2 text-[13px] text-gray-500 leading-relaxed max-w-sm">
            Securely managing the university&apos;s innovation and research assets.
          </p>
        </div>

        <div className="relative z-10 flex gap-12 sm:gap-16 mt-10 lg:mt-0">
          <div>
            <div className="text-[32px] font-bold text-brand leading-none">1,200+</div>
            <div className="mt-1 text-[10px] font-bold tracking-[0.14em] text-brand uppercase">
              Registered Assets
            </div>
          </div>
          <div>
            <div className="text-[32px] font-bold text-brand leading-none">450+</div>
            <div className="mt-1 text-[10px] font-bold tracking-[0.14em] text-brand uppercase">
              Active Patents
            </div>
          </div>
        </div>

        <p className="relative z-10 text-[11px] text-gray-400 mt-8 lg:mt-0 text-center lg:text-left">
          © 2026 Cebu Institute of Technology - University
        </p>
      </div>

      <div className="flex-1 lg:w-1/2 bg-white flex items-center justify-center px-8 py-12 sm:px-12 lg:px-16 relative">
        <div className="w-full max-w-[400px]">

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
            <Link to="/signup" className="text-[#6B0F12] font-semibold hover:underline">
              Sign up
            </Link>
          </p>

        </div>
      </div>
    </div>
  );
}
