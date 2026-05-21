import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { authApi } from "@/api/auth";

type Status = "loading" | "success" | "error";

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
        setMessage("Your email has been verified! You can now sign in.");
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })
          .response?.data?.detail;
        setStatus("error");
        setMessage(detail ?? "This verification link is invalid or has already been used.");
      });
  }, [uidb64, token]);

  return (
    <div className="min-h-screen flex" style={{ fontFamily: "'Inter', sans-serif" }}>

      {/* ── Left panel ─────────────────────────────────── */}
      <div
        className="hidden md:flex md:w-[38%] bg-[#6B0F12] flex-col justify-between relative overflow-hidden"
        style={{ padding: "60px 48px", minHeight: "100vh" }}
      >
        <div className="absolute rounded-full bg-white/[0.04]"
             style={{ width: 340, height: 340, top: -80, right: -100 }} />
        <div className="absolute rounded-full bg-white/[0.06]"
             style={{ width: 260, height: 260, bottom: 60, left: -80 }} />
        <div className="absolute rounded-full bg-white/[0.04]"
             style={{ width: 180, height: 180, bottom: 200, right: 20 }} />

        <div className="relative z-10">
          <h1 className="text-[52px] font-extrabold text-white leading-tight">
            Email<br />Verification
          </h1>
          <p className="text-[14px] mt-3 leading-relaxed" style={{ color: "rgba(255,255,255,0.65)" }}>
            Confirming your identity before<br />granting access to IRIS.
          </p>
        </div>

        <div className="relative z-10 text-[11px] leading-relaxed" style={{ color: "rgba(255,255,255,0.45)" }}>
          <div>Intelligent Research &amp; IP System</div>
          <div>© 2026 Cebu Institute of Technology - University</div>
        </div>
      </div>

      {/* ── Right panel ─────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center overflow-y-auto"
           style={{ padding: "48px 40px" }}>
        <div style={{ width: "100%", maxWidth: 420 }} className="text-center">

          {/* Logo */}
          <div className="mb-8">
            <div className="text-[38px] font-extrabold tracking-[6px] text-[#6B0F12]">IRIS</div>
            <p className="text-[13px] text-gray-500 mt-1">Intelligent Research &amp; IP System</p>
          </div>

          {status === "loading" && (
            <div className="flex flex-col items-center gap-4">
              {/* Spinner */}
              <svg
                className="animate-spin"
                style={{ width: 48, height: 48, color: "#6B0F12" }}
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle className="opacity-25" cx="12" cy="12" r="10"
                  stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="text-[15px] text-gray-600">Verifying your email…</p>
            </div>
          )}

          {status === "success" && (
            <div className="flex flex-col items-center gap-5">
              {/* Success icon */}
              <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center">
                <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-[22px] font-bold text-gray-900">Email Verified!</h2>
              <p className="text-[14px] text-gray-500 leading-relaxed">{message}</p>
              <Link
                to="/login"
                className="inline-block mt-2 px-8 py-3 rounded-lg bg-[#6B0F12] text-white
                  text-[15px] font-semibold hover:bg-[#7d1215] transition-colors"
              >
                Sign In
              </Link>
            </div>
          )}

          {status === "error" && (
            <div className="flex flex-col items-center gap-5">
              {/* Error icon */}
              <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
                <svg className="w-8 h-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h2 className="text-[22px] font-bold text-gray-900">Verification Failed</h2>
              <p className="text-[14px] text-gray-500 leading-relaxed">{message}</p>
              <div className="flex gap-3 mt-2">
                <Link
                  to="/login"
                  className="px-6 py-2.5 rounded-lg border border-gray-300 text-gray-700
                    text-[14px] font-medium hover:bg-gray-50 transition-colors"
                >
                  Sign In
                </Link>
                <Link
                  to="/signup"
                  className="px-6 py-2.5 rounded-lg bg-[#6B0F12] text-white
                    text-[14px] font-semibold hover:bg-[#7d1215] transition-colors"
                >
                  Sign Up Again
                </Link>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
