import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { TONES } from "@/components/ui/statusTones";

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
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[14px] font-medium transition-colors
            ${mode === "search"
              ? "bg-brand text-white"
              : "bg-stone-100 text-stone-700 hover:bg-stone-200"
            }`}
        >
          <i className="fa fa-search" aria-hidden />
          Semantic Search
          <span className={`px-1.5 py-0.5 text-[9px] font-bold rounded-full uppercase tracking-wider leading-none ${TONES.attention}`}>
            soon
          </span>
        </button>
        <button
          type="button"
          onClick={() => setMode("ask")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[14px] font-medium transition-colors
            ${mode === "ask"
              ? "bg-brand text-white"
              : "bg-stone-100 text-stone-700 hover:bg-stone-200"
            }`}
        >
          <i className="fa fa-robot" aria-hidden />
          Ask a Question
          <span className={`px-1.5 py-0.5 text-[9px] font-bold rounded-full uppercase tracking-wider leading-none ${TONES.attention}`}>
            soon
          </span>
        </button>
      </div>

      {/* ── Ask a Question — Coming Soon panel ──────────────────────────── */}
      {mode === "ask" && (
        <div className="flex flex-col items-center text-center py-16 px-6 bg-surface rounded-xl border border-stone-200">
          <div className="w-14 h-14 rounded-full bg-stone-50 border border-stone-200 flex items-center justify-center mb-5">
            <i className="fas fa-robot text-2xl text-stone-600" aria-hidden />
          </div>
          <span className={`px-3 py-1 text-[12px] font-bold rounded-full uppercase tracking-wider mb-4 ${TONES.attention}`}>
            Coming Soon
          </span>
          <p className="text-[14px] text-stone-600 leading-relaxed max-w-sm">
            RAG-powered Q&amp;A — ask a question and get an AI-generated answer with citations
            from the research corpus — is currently being developed.
          </p>
        </div>
      )}

      {/* ── Semantic Search — Coming Soon panel ─────────────────────────── */}
      {mode === "search" && (
        <div className="flex flex-col items-center text-center py-16 px-6 bg-surface rounded-xl border border-stone-200">
          <div className="w-14 h-14 rounded-full bg-stone-50 border border-stone-200 flex items-center justify-center mb-5">
            <i className="fas fa-search text-2xl text-stone-600" aria-hidden />
          </div>
          <span className={`px-3 py-1 text-[12px] font-bold rounded-full uppercase tracking-wider mb-4 ${TONES.attention}`}>
            Coming Soon
          </span>
          <p className="text-[14px] text-stone-600 leading-relaxed max-w-sm">
            Semantic search — find research records by meaning using vector embeddings and
            pgvector similarity queries — is currently being developed.
          </p>
        </div>
      )}
    </div>
  );
}
