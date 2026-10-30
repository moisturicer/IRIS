import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { authApi } from "@/api/auth";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button, Input } from "@/components/ui";
import { classifyRecoveryFailure, retryMessage, useNoReferrer, useSecondsUntil } from "./recovery";

const INVALID_LINK =
  "This link is invalid or no longer available. Request a new email.";
const POLICY =
  "At least 8 characters, and not a common or all-numeric password. Spaces count.";

type FieldErrors = Partial<Record<"new_password" | "confirm_password", string>>;

/**
 * Read the token from the fragment (ADR-045 §3). It lives only in this
 * component's memory from then on: never in storage, never in a URL another
 * page could see, and never sent anywhere until the person submits. Reading
 * has no side effect, so StrictMode's second mount in development still finds
 * it; `useStripFragment` removes it from the address bar after mounting.
 */
function readTokenFromFragment(): string {
  const match = /^#token=([A-Za-z0-9_-]+)$/.exec(window.location.hash);
  return match ? match[1] : "";
}

function useStripFragment(): void {
  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
    }
  }, []);
}

function PasswordToggle({ shown, label, onToggle }: { shown: boolean; label: string; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={`${shown ? "Hide" : "Show"} ${label}`}
      // 44px target, like the sign-in screen's toggle (2.5.5).
      className="flex items-center justify-center min-h-11 min-w-11 px-1 text-[14px] font-semibold text-brand hover:underline"
    >
      {shown ? "Hide" : "Show"}
    </button>
  );
}

/**
 * Choose a new password from an emailed link (IR-642, ADR-045 §7).
 *
 * Every link that cannot be used -- invalid, expired, used, revoked -- gets the
 * same guidance, because the server deliberately does not say which. Success
 * returns the person to sign-in: a reset never signs anyone in.
 */
export default function ResetPasswordPage() {
  useNoReferrer();
  useStripFragment();
  const [token, setToken] = useState(readTokenFromFragment);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [shown, setShown] = useState({ password: false, confirm: false });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [waitUntil, setWaitUntil] = useState<number | null>(null);
  const left = useSecondsUntil(waitUntil);
  const [done, setDone] = useState<string | null>(null);
  const [linkInvalid, setLinkInvalid] = useState(() => token === "");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);

  // Nothing secret outlives the screen that needed it.
  const forget = () => {
    setToken("");
    setPassword("");
    setConfirm("");
  };

  useEffect(() => {
    if (done || (linkInvalid && token === "" && headingRef.current)) headingRef.current?.focus();
  }, [done, linkInvalid, token]);

  useEffect(() => {
    if (problem || Object.keys(errors).length) summaryRef.current?.focus();
  }, [problem, errors]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting || left > 0) return;
    const missing: FieldErrors = {};
    if (!password) missing.new_password = "Enter a new password.";
    if (!confirm) missing.confirm_password = "Enter the new password again.";
    setProblem(null);
    setErrors(missing);
    if (Object.keys(missing).length) return;

    setSubmitting(true);
    try {
      const { data } = await authApi.confirmPasswordReset({
        token, new_password: password, confirm_password: confirm,
      });
      forget();
      setDone(data?.detail ?? "Password updated. Sign in with your new password.");
    } catch (error) {
      const failure = classifyRecoveryFailure(error);
      if (failure.kind === "invalid_link") {
        forget();
        setLinkInvalid(true);
      } else if (failure.kind === "validation") {
        // The server is authoritative: its messages are shown as it wrote them.
        setErrors({
          new_password: failure.errors.new_password?.join(" "),
          confirm_password: failure.errors.confirm_password?.join(" "),
        });
      } else {
        setProblem(retryMessage(failure));
        if (failure.kind === "rate_limited" || failure.kind === "unavailable") {
          setWaitUntil(Date.now() + failure.retryAfter * 1000);
        }
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <AuthLayout variant="login">
        <h2 ref={headingRef} tabIndex={-1}
          className="text-balance font-display text-display font-semibold text-stone-900 outline-none">
          Password updated
        </h2>
        <p className="mt-3 text-[15px] leading-relaxed text-stone-700">{done}</p>
        <p className="mt-3 text-[14px] leading-relaxed text-stone-600">
          Every device that was signed in has been signed out. Email verification, role approval and
          any account restrictions still apply.
        </p>
        <p className="mt-6 text-[15px]">
          <Link to="/login" className="font-semibold text-brand hover:underline">Return to sign in</Link>
        </p>
      </AuthLayout>
    );
  }

  if (linkInvalid) {
    return (
      <AuthLayout variant="login">
        <h2 ref={headingRef} tabIndex={-1}
          className="text-balance font-display text-display font-semibold text-stone-900 outline-none">
          This link can&apos;t be used
        </h2>
        <p className="mt-3 text-[15px] leading-relaxed text-stone-700">{INVALID_LINK}</p>
        <div className="mt-6 flex flex-col gap-3 text-[15px]">
          <Link to="/password/forgot" className="font-semibold text-brand hover:underline">Request a new email</Link>
          <Link to="/login" className="font-semibold text-brand hover:underline">Back to sign in</Link>
        </div>
      </AuthLayout>
    );
  }

  const summary = problem ?? [errors.new_password, errors.confirm_password].filter(Boolean).join(" ");

  return (
    <AuthLayout variant="login">
      <h2 className="text-balance font-display text-display font-semibold text-stone-900">
        Choose a new password
      </h2>
      <p className="mt-2 mb-6 text-[15px] leading-relaxed text-stone-600">
        You will sign in with it from now on. Every device signed in to your account will be signed out.
      </p>
      {summary && (
        <AuthAlert variant="error" title={problem ? "Check your request" : "Check the password"} focusRef={summaryRef}>
          {summary}
        </AuthAlert>
      )}
      <form className="flex flex-col gap-5" noValidate onSubmit={submit}>
        <Input
          id="reset-new-password"
          label="New password"
          size="lg"
          type={shown.password ? "text" : "password"}
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={errors.new_password}
          hint={POLICY}
          required
          trailing={<PasswordToggle shown={shown.password} label="new password"
            onToggle={() => setShown((s) => ({ ...s, password: !s.password }))} />}
        />
        <Input
          id="reset-confirm-password"
          label="Confirm new password"
          size="lg"
          type={shown.confirm ? "text" : "password"}
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
          error={errors.confirm_password}
          required
          trailing={<PasswordToggle shown={shown.confirm} label="confirmation"
            onToggle={() => setShown((s) => ({ ...s, confirm: !s.confirm }))} />}
        />
        <Button type="submit" variant="primary" size="full" loading={submitting} disabled={left > 0}>
          {left > 0 ? `Set new password (in ${left} seconds)` : "Set new password"}
        </Button>
        <p role="status" className="sr-only">{submitting ? "Saving your new password…" : ""}</p>
      </form>
    </AuthLayout>
  );
}
