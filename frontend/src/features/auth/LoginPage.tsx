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
import { AuthLayout } from "@/components/auth/AuthLayout";

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

    </AuthLayout>
  );
}
