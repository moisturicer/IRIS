import { useLocation } from "react-router-dom";
import { authApi } from "@/api/auth";
import { EmailRequestForm, type EmailRequestCopy } from "./EmailRequestForm";

const COPY: EmailRequestCopy = {
  tab: "Email verification",
  heading: "Send a new verification email",
  intro: "Enter the email address you registered with. If it still needs verifying, we will send it a new link. "
    + "You do not need to register again.",
  submit: "Send verification email",
  // ADR-045 §6, word for word.
  guidance: "Email may take a few minutes. Check spam, try again after 60 seconds, or contact RDCO or your "
    + "department administrator.",
};

/**
 * "Resend verification email" (IR-643, ADR-045 §7), reached from sign-in,
 * registration's confirmation and a link that no longer works.
 *
 * The address may arrive in router state from a screen where the person
 * typed it, so it never appears in a URL. Nothing here reads it from a link.
 */
export default function ResendVerificationPage() {
  const state = useLocation().state as { email?: unknown } | null;
  const initialEmail = typeof state?.email === "string" ? state.email : "";
  return (
    <EmailRequestForm
      id="resend-email"
      copy={COPY}
      request={authApi.resendVerification}
      initialEmail={initialEmail}
    />
  );
}
