import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { useUIStore } from "@/store/ui.store";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { AccountLockedModal } from "@/components/auth/AccountLockedModal";
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
import irisLogo from "@/assets/images/iris_logo.png";

const LOCKOUT_MS = 15 * 60 * 1000;

const schema = z.object({
  email:    z.string().min(1, "Email is required.").email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

type FormData = z.infer<typeof schema>;

type LoginAlert =
  | { kind: "credentials" }
  | { kind: "unverified" }
  | { kind: "generic"; message: string };

const inputBase =
  "w-full rounded-lg px-4 py-3 text-[14px] bg-[#F3F3F3] outline-none transition-colors placeholder:text-gray-400 text-gray-900 border focus:bg-white";
const inputOk   = "border-transparent focus:border-brand";
const inputErr  = "border-brand bg-red-50/50 focus:border-brand";

export default function LoginPage() {
  const navigate       = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { login }      = useAuth();
  const { addToast }   = useUIStore();
  const [showPassword, setShowPassword] = useState(false);
  const [loginAlert, setLoginAlert]     = useState<LoginAlert | null>(null);
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [lockoutOpen, setLockoutOpen]   = useState(false);
  const [lockoutUntil, setLockoutUntilState] = useState<number | undefined>();
  const [lockoutEmail, setLockoutEmail] = useState("");
  const [sessionAlert, setSessionAlert] = useState(
    () => searchParams.get("reason") === "session_expired"
  );

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const email = watch("email");

  useEffect(() => {
    if (searchParams.get("reason") === "session_expired") {
      setSessionAlert(true);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!email) return;
    const until = getLockoutUntil(email);
    if (until) {
      setLockoutEmail(email);
      setLockoutUntilState(until);
      setLockoutOpen(true);
    }
    setFailedAttempts(getLoginAttempts(email));
  }, [email]);

  const dismissSessionAlert = () => {
    setSessionAlert(false);
    if (searchParams.get("reason")) {
      searchParams.delete("reason");
      setSearchParams(searchParams, { replace: true });
    }
  };

  const openLockout = (forEmail: string, untilMs: number) => {
    setLockoutUntil(forEmail, untilMs);
    setLockoutEmail(forEmail);
    setLockoutUntilState(untilMs);
    setLockoutOpen(true);
    setLoginAlert(null);
  };

  const closeLockout = () => {
    setLockoutOpen(false);
    if (lockoutEmail && lockoutUntil && lockoutUntil <= Date.now()) {
      clearLockout(lockoutEmail);
    }
  };

  const onSubmit = async (data: FormData) => {
    setLoginAlert(null);

    if (isAccountLocked(data.email)) {
      openLockout(data.email, getLockoutUntil(data.email)!);
      return;
    }

    try {
      const res = await authApi.login({ username: data.email, password: data.password });
      resetLoginAttempts(data.email);
      clearLockout(data.email);
      login(res.data.user, res.data.access, res.data.refresh);
      navigate("/");
    } catch (err: unknown) {
      const res = (err as { response?: { status?: number; data?: { detail?: string } } }).response;
      const detail = res?.data?.detail ?? "Invalid email or password.";
      const status = res?.status;
      const detailLower = detail.toLowerCase();

      const locked =
        status === 403 &&
        (detailLower.includes("locked") || detailLower.includes("locked out"));

      if (locked) {
        openLockout(data.email, Date.now() + LOCKOUT_MS);
        return;
      }

      if (status === 403 && detailLower.includes("not verified")) {
        setLoginAlert({ kind: "unverified" });
        return;
      }

      const attempts = incrementLoginAttempts(data.email);
      setFailedAttempts(attempts);

      if (attempts >= LOGIN_FAILURE_LIMIT) {
        openLockout(data.email, Date.now() + LOCKOUT_MS);
        return;
      }

      if (detail === "Invalid credentials." || status === 401) {
        setLoginAlert({ kind: "credentials" });
      } else {
        setLoginAlert({ kind: "generic", message: detail });
      }
    }
  };

  const showFieldError = loginAlert !== null && !lockoutOpen;
  const inputState = showFieldError ? inputErr : inputOk;

  return (
    <div className="min-h-screen flex flex-col lg:flex-row font-sans relative">

      <AccountLockedModal
        open={lockoutOpen}
        onClose={closeLockout}
        unlockAt={lockoutUntil}
      />

      {/* ── Left: branding ─────────────────────────────────────────── */}
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

      {/* ── Right: login form ──────────────────────────────────────── */}
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

          <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>

            <div>
              <label htmlFor="login-email" className="block text-[13px] font-semibold text-gray-900 mb-2">
                Email Address
              </label>
              <input
                id="login-email"
                {...register("email")}
                type="email"
                autoComplete="email"
                placeholder="student@cit.edu"
                disabled={lockoutOpen}
                className={`${inputBase} ${inputState} ${errors.email ? inputErr : ""}`}
              />
              {errors.email && (
                <p className="text-[12px] text-red-600 mt-1.5">{errors.email.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="login-password" className="block text-[13px] font-semibold text-gray-900 mb-2">
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  {...register("password")}
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  disabled={lockoutOpen}
                  className={`${inputBase} pr-16 ${inputState} ${errors.password ? inputErr : ""}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-[13px] font-semibold text-brand hover:underline"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {errors.password && (
                <p className="text-[12px] text-red-600 mt-1.5">{errors.password.message}</p>
              )}
            </div>

            <div className="flex justify-end -mt-1">
              <button
                type="button"
                className="text-[13px] font-semibold text-brand hover:underline"
                onClick={() =>
                  addToast({
                    type: "info",
                    message: "Password reset is not available yet. Contact your administrator.",
                  })
                }
              >
                Forgot password?
              </button>
            </div>

            <button
              type="submit"
              disabled={isSubmitting || lockoutOpen}
              className="w-full py-3.5 rounded-lg text-[15px] font-semibold text-white transition-colors
                bg-gold hover:bg-gold-dark disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {isSubmitting ? "Signing in…" : "Sign In"}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-gray-200 text-center">
            <p className="text-[14px] text-gray-500">
              Don&apos;t have an account?{" "}
              <Link to="/signup" className="font-semibold text-brand hover:underline">
                Register here
              </Link>
            </p>
          </div>

        </div>
      </div>
    </div>
  );
}
