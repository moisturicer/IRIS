import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { downloadBlob, filenameFromDisposition } from "@/lib/utils";

type PageState = "loading" | "success" | "error";

export default function DownloadTokenPage() {
  const [params] = useSearchParams();
  const token    = params.get("token") ?? "";

  const [state, setState]   = useState<PageState>("loading");
  const [message, setMessage] = useState("Preparing your download…");

  useEffect(() => {
    if (!token) {
      setState("error");
      setMessage("Missing download token. Use the link from your approval email or notification.");
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const { data, headers } = await recordsApi.redeemDownloadToken(token);
        if (cancelled) return;

        const name =
          filenameFromDisposition(headers["content-disposition"])
          ?? "iris-record-download.pdf";
        downloadBlob(data, name);
        setState("success");
        setMessage(`Download started (${name}). Check your browser downloads folder.`);
      } catch (err: unknown) {
        if (cancelled) return;
        const detail =
          (err as { response?: { data?: Blob | { detail?: string } } }).response?.data;
        let text = "This download link is invalid or has expired.";
        if (detail instanceof Blob) {
          try {
            const raw = await detail.text();
            const parsed = JSON.parse(raw) as { detail?: string };
            if (parsed.detail) text = parsed.detail;
          } catch {
            /* keep default */
          }
        } else if (detail && typeof detail === "object" && "detail" in detail && detail.detail) {
          text = String(detail.detail);
        }
        setState("error");
        setMessage(text);
      }
    })();

    return () => { cancelled = true; };
  }, [token]);

  return (
    <div className="min-h-screen bg-[#F5F0E8] flex items-center justify-center p-6">
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm w-full max-w-md p-8 text-center">
        {state === "loading" && (
          <div className="mx-auto w-10 h-10 border-2 border-[#6B0F12]/30 border-t-[#6B0F12] rounded-full animate-spin mb-4" />
        )}
        {state === "success" && (
          <div className="mx-auto w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mb-4">
            <i className="fas fa-check text-green-600 text-lg" aria-hidden />
          </div>
        )}
        {state === "error" && (
          <div className="mx-auto w-12 h-12 rounded-full bg-red-100 flex items-center justify-center mb-4">
            <i className="fas fa-exclamation text-red-600 text-lg" aria-hidden />
          </div>
        )}

        <h1 className="text-[18px] font-bold text-gray-900 mb-2">
          {state === "loading" ? "Downloading" : state === "success" ? "Download ready" : "Download failed"}
        </h1>
        <p className="text-[13px] text-gray-600 leading-relaxed">{message}</p>

        <Link
          to="/"
          className="inline-block mt-6 text-[13px] font-semibold text-[#6B0F12] hover:underline"
        >
          Back to Discover
        </Link>
      </div>
    </div>
  );
}
