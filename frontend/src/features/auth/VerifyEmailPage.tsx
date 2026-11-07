import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { authApi } from "@/api/auth";
import { AuthAlert } from "@/components/auth/AuthAlert";
import { EntryFrame, EntryTab } from "@/components/auth/EntryFrame";
import { Button } from "@/components/ui";
import { classifyRecoveryFailure, retryMessage, useNoReferrer, useSecondsUntil } from "./recovery";

const INVALID_LINK = "This link is invalid or no longer available. Request a new email.";
const VERIFIED = "Email verified. Return to sign-in.";

/**
 * Read the token from `#token=…` (ADR-045 §3). From then on it lives only in
 * this component's memory: never in storage, never in a URL. Reading has no
 * side effect, so StrictMode's second mount in development still finds it.
 */
function readTokenFromFragment(): string {
  const match = /^#token=([A-Za-z0-9_-]+)$/.exec(window.location.hash);
  return match ? match[1] : "";
}

/**
 * Replace the address with the bare `/verify-email`, whatever it was. That
 * strips the fragment, and also the secret in an old `/activate/<uid>/<token>`
 * path, which this page answers too: those links are retired (IR-643).
 */
function useForgetAddress(): void {
  useEffect(() => {
    window.history.replaceState(window.history.state, "", "/verify-email");
  }, []);
}

/**
 * Where a verification email's link lands (IR-643, ADR-045 §3, §7).
 *
 * Opening the page changes nothing: a mail scanner or a link preview that
 * fetches it verifies no one. The person presses "Verify email", and that one
 * POST is what verifies. Every link that cannot be used -- invalid, expired,
 * used, replaced by a newer email, or an old `/activate` link -- gets the same
 * guidance and a way to ask for a new email, because the server deliberately
 * does not say which. Verifying signs no one in, and RDCO's approval may still
 * be pending, so success points back to sign-in and says so.
 */
export default function VerifyEmailPage() {
  useNoReferrer();
  useForgetAddress();
  const [token, setToken] = useState(readTokenFromFragment);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [waitUntil, setWaitUntil] = useState<number | null>(null);
  const left = useSecondsUntil(waitUntil);
  const [done, setDone] = useState<string | null>(null);
  const [linkInvalid, setLinkInvalid] = useState(() => token === "");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const problemRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (done || linkInvalid) headingRef.current?.focus();
  }, [done, linkInvalid]);

  useEffect(() => {
    if (problem) problemRef.current?.focus();
  }, [problem]);

  const verify = async () => {
    if (submitting || left > 0) return;
    setProblem(null);
    setSubmitting(true);
    try {
      const { data } = await authApi.confirmVerification(token);
      setToken("");
      setDone(data?.detail ?? VERIFIED);
    } catch (error) {
      const failure = classifyRecoveryFailure(error);
      if (failure.kind === "invalid_link" || failure.kind === "validation") {
        setToken("");
        setLinkInvalid(true);
      } else {
        // Unknown outcome on a dropped connection: the same link is retried.
        // If the first attempt did verify, the retry is refused as used, which
        // still points the person back to sign-in.
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
      <EntryFrame tabs={<EntryTab>Email verification</EntryTab>}>
        <h2 ref={headingRef} tabIndex={-1}
          className="text-balance font-display text-display font-semibold text-stone-900 outline-none">
          Email verified
        </h2>
        <p className="mt-3 text-body text-stone-700">{done}</p>
        <p className="mt-3 text-small text-stone-600">
          An administrator may still need to approve your account. Signing in shows whether your
          request is waiting.
        </p>
        <p className="mt-6 text-body">
          <Link to="/login" className="font-semibold text-brand hover:underline">Return to sign in</Link>
        </p>
      </EntryFrame>
    );
  }

  if (linkInvalid) {
    return (
      <EntryFrame tabs={<EntryTab>Email verification</EntryTab>}>
        <h2 ref={headingRef} tabIndex={-1}
          className="text-balance font-display text-display font-semibold text-stone-900 outline-none">
          This link can&apos;t be used
        </h2>
        <p className="mt-3 text-body text-stone-700">{INVALID_LINK}</p>
        <p className="mt-3 text-small text-stone-600">
          If your email is already verified, you can sign in.
        </p>
        <div className="mt-6 flex flex-col gap-3 text-body">
          <Link to="/verify-email/resend" className="font-semibold text-brand hover:underline">
            Resend verification email
          </Link>
          <Link to="/login" className="font-semibold text-brand hover:underline">Back to sign in</Link>
        </div>
      </EntryFrame>
    );
  }

  return (
    <EntryFrame tabs={<EntryTab>Email verification</EntryTab>}>
      <h2 className="text-balance font-display text-display font-semibold text-stone-900">
        Verify your email
      </h2>
      <p className="mt-2 mb-6 text-body text-stone-600">
        Confirm that this email address is yours. This does not sign you in.
      </p>
      {problem && (
        <AuthAlert variant="error" title="Check your request" focusRef={problemRef}>{problem}</AuthAlert>
      )}
      <Button
        type="button"
        variant="primary"
        size="full"
        loading={submitting}
        disabled={left > 0}
        onClick={() => void verify()}
      >
        {left > 0 ? `Verify email (in ${left} seconds)` : "Verify email"}
      </Button>
      <p role="status" className="mt-3 text-small text-stone-600">{submitting ? "Verifying…" : ""}</p>
      <p className="mt-6 text-body">
        <Link to="/login" className="font-semibold text-brand hover:underline">Back to sign in</Link>
      </p>
    </EntryFrame>
  );
}
