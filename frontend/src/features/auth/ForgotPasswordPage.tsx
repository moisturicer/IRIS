import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { authApi } from "@/api/auth";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { Button, Input } from "@/components/ui";
import { classifyRecoveryFailure, retryMessage, useSecondsUntil } from "./recovery";

/** ADR-045 §2: the server's generic answer, shown whatever the address. */
const FALLBACK_RECEIVED =
  "If this address is eligible, an email will arrive shortly. You can try again after 60 seconds.";
const DELIVERY_GUIDANCE =
  "Email may take a few minutes. Check spam, try again after 60 seconds, or contact RDCO or your department administrator.";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function emailProblem(value: string): string | undefined {
  const email = value.trim();
  if (!email) return "Enter your email address.";
  if (!EMAIL_PATTERN.test(email)) return "Enter a valid email address.";
  return undefined;
}

/**
 * "Forgot password?" (IR-642, ADR-045 §7).
 *
 * Says the same thing for every address, because the server does: whether an
 * account exists, is locked or was sent anything is never shown here. What
 * the screen does own is honest timing -- a visible cooldown that is announced
 * once when it ends, and a network failure reported as an unknown outcome,
 * since the request may have been accepted before the connection dropped.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [waitUntil, setWaitUntil] = useState<number | null>(null);
  const [counted, setCounted] = useState(false);
  const left = useSecondsUntil(waitUntil);
  const confirmationRef = useRef<HTMLHeadingElement>(null);
  const problemRef = useRef<HTMLDivElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (sent) confirmationRef.current?.focus();
  }, [sent]);

  useEffect(() => {
    if (left > 0) setCounted(true);
  }, [left]);

  // ADR-045 §7: focus moves to what needs attention.
  useEffect(() => {
    if (problem) problemRef.current?.focus();
  }, [problem]);

  const send = async () => {
    setProblem(null);
    setSending(true);
    try {
      const { data } = await authApi.requestPasswordReset(email.trim());
      setSent(data?.detail ?? FALLBACK_RECEIVED);
      setCounted(false);
      setWaitUntil(Date.now() + (data?.retry_after ?? 60) * 1000);
    } catch (error) {
      const failure = classifyRecoveryFailure(error);
      if (failure.kind === "validation") {
        setFieldError(failure.errors.email?.join(" ") ?? "Enter a valid email address.");
        emailRef.current?.focus();
      } else {
        setProblem(retryMessage(failure));
        if (failure.kind === "rate_limited" || failure.kind === "unavailable") {
          setWaitUntil(Date.now() + failure.retryAfter * 1000);
        }
      }
    } finally {
      setSending(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const invalid = emailProblem(email);
    setFieldError(invalid);
    if (invalid) emailRef.current?.focus();
    if (!invalid && !sending && left === 0) void send();
  };

  if (sent) {
    return (
      <AuthLayout variant="login">
        <h2
          ref={confirmationRef}
          tabIndex={-1}
          className="text-balance font-display text-display font-semibold text-stone-900 outline-none"
        >
          Check your email
        </h2>
        <p className="mt-3 text-[15px] leading-relaxed text-stone-700">{sent}</p>
        <p className="mt-3 text-[14px] leading-relaxed text-stone-600">{DELIVERY_GUIDANCE}</p>
        {problem && (
          <div className="mt-6">
            <AuthAlert variant="error" title="Check your request" focusRef={problemRef}>{problem}</AuthAlert>
          </div>
        )}
        <div className="mt-6 flex flex-col gap-4">
          <Button
            type="button"
            variant="outline"
            size="full"
            loading={sending}
            disabled={left > 0}
            onClick={() => void send()}
          >
            {left > 0 ? `Send another email in ${left} seconds` : "Send another email"}
          </Button>
          <p role="status" className="text-[14px] text-stone-600">
            {sending ? "Sending…" : counted && left === 0 ? "You can request another email now." : ""}
          </p>
          <Link to="/login" className="text-[15px] font-semibold text-brand hover:underline">
            Back to sign in
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout variant="login">
      <h2 className="text-balance font-display text-display font-semibold text-stone-900">
        Reset your password
      </h2>
      <p className="mt-2 mb-6 text-[15px] leading-relaxed text-stone-600">
        Enter the email address you sign in with. If it belongs to an account that can be reset,
        we will send it a link.
      </p>
      {problem && <AuthAlert variant="error" title="Check your request" focusRef={problemRef}>{problem}</AuthAlert>}
      <form className="flex flex-col gap-5" noValidate onSubmit={submit}>
        <Input
          id="forgot-email"
          ref={emailRef}
          label="Email Address"
          size="lg"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldError}
          required
        />
        <Button type="submit" variant="primary" size="full" loading={sending} disabled={left > 0}>
          {left > 0 && problem ? `Send reset email (in ${left} seconds)` : "Send reset email"}
        </Button>
        <p role="status" className="text-[14px] text-stone-600">{sending ? "Sending…" : ""}</p>
      </form>
      <p className="mt-6 text-[15px]">
        <Link to="/login" className="font-semibold text-brand hover:underline">Back to sign in</Link>
      </p>
    </AuthLayout>
  );
}
