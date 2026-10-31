/**
 * Where the link in a registration email lands (IR-538).
 *
 * It renders on the Dossier frame's sheet under an "Email verification" tab,
 * without the editorial lede and without a masthead cross-link: the sheet
 * already offers every way on (IR-710). The result changes inside one polite
 * live region, title and reason together, so a screen-reader user hears how the check ended rather than
 * being left on "Verifying Email". A verified email does not open the account:
 * RDCO approves it next, and the success copy says so.
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { authApi } from "@/api/auth";
import { EntryFrame, EntryTab } from "@/components/auth/EntryFrame";
import { ButtonLink } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { cn } from "@/lib/utils";

type Status = "loading" | "success" | "error";

const TITLES: Record<Status, string> = {
  loading: "Verifying Email",
  success: "Email Verified",
  error:   "Verification Failed",
};

const SUCCESS_MESSAGE =
  "Your email address is verified. RDCO now reviews your account and emails you when they decide. " +
  "Until then, signing in shows that your account is waiting for approval.";

const FALLBACK_FAILURE = "This verification link is invalid or has already been used.";

/** Decorative: the title beside it carries the meaning, so it is hidden from assistive technology. */
function StatusMark({ status }: { status: Status }) {
  if (status === "loading") return <Spinner size="lg" />;

  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-12 items-center justify-center rounded-full text-white",
        status === "success" ? "bg-stone-900" : "bg-brand",
      )}
    >
      <i className={cn("fas text-lg", status === "success" ? "fa-check" : "fa-xmark")} />
    </span>
  );
}

export default function EmailVerifyPage() {
  const { uidb64, token } = useParams<{ uidb64: string; token: string }>();
  const [status, setStatus]   = useState<Status>("loading");
  const [message, setMessage] = useState("Checking your verification link.");

  useEffect(() => {
    if (!uidb64 || !token) {
      setStatus("error");
      setMessage("Invalid verification link.");
      return;
    }

    authApi.activate(uidb64, token)
      .then(() => {
        setStatus("success");
        setMessage(SUCCESS_MESSAGE);
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setStatus("error");
        setMessage(detail ?? FALLBACK_FAILURE);
      });
  }, [uidb64, token]);

  return (
    <EntryFrame tabs={<EntryTab>Email verification</EntryTab>}>
      <StatusMark status={status} />

      {/* Present from the first render, so the change to a result is announced. */}
      <div role="status" className="mt-6">
        <h2 className="text-balance font-display text-display font-semibold text-stone-900">
          {TITLES[status]}
        </h2>
        <p className="mt-3 text-pretty text-body text-stone-700">{message}</p>
      </div>

      {status === "success" && (
        <div className="mt-section-lg">
          <ButtonLink to="/login" size="full">Sign in</ButtonLink>
        </div>
      )}

      {status === "error" && (
        <div className="mt-section-lg flex flex-col gap-3">
          <ButtonLink to="/signup" size="full">Register again</ButtonLink>
          <ButtonLink to="/login" variant="outline" size="full">Sign in</ButtonLink>
        </div>
      )}
    </EntryFrame>
  );
}
