import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";

type Mode = "search" | "ask";

export default function AIHubPage() {
  const [mode, setMode] = useState<Mode>("search");

  return (
    <div>
      <PageHeader
        title="AI Research Hub"
        description="Search research records by meaning, or ask a question about the research corpus."
      />

      {/* Mode toggle */}
      <div className="flex gap-2 mb-5">
        <button
          type="button"
          onClick={() => setMode("search")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-medium transition-colors
            ${mode === "search"
              ? "bg-[#6B0F12] text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
        >
          <i className="fa fa-search" />
          Semantic Search
          <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold rounded-full border border-amber-200 uppercase tracking-wider leading-none">
            soon
          </span>
        </button>
        <button
          type="button"
          onClick={() => setMode("ask")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-medium transition-colors
            ${mode === "ask"
              ? "bg-[#6B0F12] text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
        >
          <i className="fa fa-robot" />
          Ask a Question
          <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold rounded-full border border-amber-200 uppercase tracking-wider leading-none">
            soon
          </span>
        </button>
      </div>

      {/* ── Ask a Question — Coming Soon panel ──────────────────────────── */}
      {mode === "ask" && (
        <div className="flex flex-col items-center text-center py-16 px-6 bg-white rounded-xl border border-gray-200">
          <div className="w-14 h-14 rounded-full bg-slate-50 border border-slate-100 flex items-center justify-center mb-5">
            <i className="fas fa-robot text-2xl text-slate-300" />
          </div>
          <span className="px-3 py-1 bg-amber-50 text-amber-700 text-[11px] font-bold rounded-full border border-amber-200 uppercase tracking-wider mb-4">
            Coming Soon
          </span>
          <p className="text-[13px] text-gray-500 leading-relaxed max-w-sm">
            RAG-powered Q&amp;A — ask a question and get an AI-generated answer with citations
            from the research corpus — is currently being developed.
          </p>
        </div>
      )}

      {/* ── Semantic Search — Coming Soon panel ─────────────────────────── */}
      {mode === "search" && (
        <div className="flex flex-col items-center text-center py-16 px-6 bg-white rounded-xl border border-gray-200">
          <div className="w-14 h-14 rounded-full bg-slate-50 border border-slate-100 flex items-center justify-center mb-5">
            <i className="fas fa-search text-2xl text-slate-300" />
          </div>
          <span className="px-3 py-1 bg-amber-50 text-amber-700 text-[11px] font-bold rounded-full border border-amber-200 uppercase tracking-wider mb-4">
            Coming Soon
          </span>
          <p className="text-[13px] text-gray-500 leading-relaxed max-w-sm">
            Semantic search — find research records by meaning using vector embeddings and
            pgvector similarity queries — is currently being developed.
          </p>
        </div>
      )}
    </div>
  );
}
