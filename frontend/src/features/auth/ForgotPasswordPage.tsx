import { authApi } from "@/api/auth";
import { EmailRequestForm, type EmailRequestCopy } from "./EmailRequestForm";

const COPY: EmailRequestCopy = {
  tab: "Password recovery",
  heading: "Reset your password",
  intro: "Enter the email address you sign in with. If it belongs to an account that can be reset, we will send it a link.",
  submit: "Send reset email",
  guidance: "Email may take a few minutes. Check spam, try again after 60 seconds, or contact an administrator.",
};

/** "Forgot password?" (IR-642, ADR-045 §7). The form is `EmailRequestForm`. */
export default function ForgotPasswordPage() {
  return <EmailRequestForm id="forgot-email" copy={COPY} request={authApi.requestPasswordReset} />;
}
