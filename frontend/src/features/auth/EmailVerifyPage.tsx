import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { authApi } from "@/api/auth";
import irisLogo from "@/assets/images/iris_logo.png";

type Status = "loading" | "success" | "error";

function StatusIcon({ status }: { status: "loading" | "success" | "error" }) {
  if (status === "loading") {
    return (
      <svg
        className="animate-spin h-12 w-12 text-brand"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        aria-hidden
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
    );
  }

  if (status === "success") {
    return (
      <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center">
        <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
        </svg>
      </div>
    );
  }

  return (
    <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
      <svg className="w-8 h-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </div>
  );
}

export default function EmailVerifyPage() {
  const { uidb64, token } = useParams<{ uidb64: string; token: string }>();
  const [status, setStatus]   = useState<Status>("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!uidb64 || !token) {
      setStatus("error");
      setMessage("Invalid verification link.");
      return;
    }

    authApi.activate(uidb64, token)
      .then(() => {
        setStatus("success");
        setMessage("Your email has been verified. You can now sign in to IRIS.");
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setStatus("error");
        setMessage(detail ?? "This verification link is invalid or has already been used.");
      });
  }, [uidb64, token]);

  const titles: Record<Status, string> = {
    loading: "Verifying Email",
    success: "Email Verified",
    error:   "Verification Failed",
  };

  const subtitles: Record<Status, string> = {
    loading: "Please wait while we confirm your account.",
    success: message,
    error:   message,
  };

  return (
    <div className="min-h-screen flex flex-col lg:flex-row font-sans">

      {/* ── Left: branding (matches login) ─────────────────────────── */}
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

          <h1 className="mt-6 font-serif leading-[1.05]">
            <span className="block text-[40px] sm:text-[44px] font-bold text-gold">Secure</span>
            <span className="block text-[40px] sm:text-[44px] font-bold text-brand">
              Your Access.
            </span>
          </h1>

          <p className="mt-5 text-[14px] text-brand/90 leading-relaxed max-w-md">
            Email verification protects your research records and ensures only authorized
            CIT-U members can access the IRIS digital vault.
          </p>

          <blockquote className="mt-8 pl-5 border-l-4 border-gold max-w-md">
            <p className="font-serif italic text-[14px] text-brand leading-relaxed">
              &ldquo;One verified identity, one trusted gateway to your intellectual property.&rdquo;
            </p>
          </blockquote>
        </div>

        <p className="relative z-10 text-[11px] text-gray-500 mt-10 lg:mt-0">
          © 2026 Cebu Institute of Technology - University
        </p>
      </div>

      {/* ── Right: verification status ─────────────────────────────── */}
      <div className="flex-1 lg:w-1/2 bg-white flex items-center justify-center px-8 py-12 sm:px-12 lg:px-16">
        <div className="w-full max-w-[400px]">

          <div className="mb-6">
            <StatusIcon status={status} />
          </div>

          <h2 className="text-[28px] font-bold text-gray-900">{titles[status]}</h2>
          <p className="mt-2 text-[14px] text-gray-500 leading-relaxed mb-8">
            {subtitles[status]}
          </p>

          {status === "loading" && (
            <p className="text-[13px] text-gray-500">
              This usually takes only a moment…
            </p>
          )}

          {status === "success" && (
            <Link
              to="/login"
              className="inline-flex w-full items-center justify-center py-3.5 rounded-lg text-[15px] font-semibold text-white
                bg-gold hover:bg-gold-dark transition-colors"
            >
              Sign In
            </Link>
          )}

          {status === "error" && (
            <div className="flex flex-col gap-3">
              <Link
                to="/signup"
                className="inline-flex w-full items-center justify-center py-3.5 rounded-lg text-[15px] font-semibold text-white
                  bg-gold hover:bg-gold-dark transition-colors"
              >
                Register Again
              </Link>
              <Link
                to="/login"
                className="inline-flex w-full items-center justify-center py-3 rounded-lg text-[14px] font-semibold text-brand
                  border border-gray-300 hover:bg-gray-50 transition-colors"
              >
                Sign In
              </Link>
            </div>
          )}

          {status !== "loading" && (
            <div className="mt-8 pt-6 border-t border-gray-200 text-center">
              <p className="text-[14px] text-gray-500">
                {status === "success" ? (
                  <>
                    Need a new account?{" "}
                    <Link to="/signup" className="font-semibold text-brand hover:underline">
                      Register here
                    </Link>
                  </>
                ) : (
                  <>
                    Already verified?{" "}
                    <Link to="/login" className="font-semibold text-brand hover:underline">
                      Sign in
                    </Link>
                  </>
                )}
              </p>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
