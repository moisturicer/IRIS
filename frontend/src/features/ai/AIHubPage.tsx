/**
 * AI Hub page -- semantic search + AI-assisted Q&A over research records.
 *
 * Two modes:
 *   1. Semantic search: returns ranked record list by embedding similarity.
 *   2. Ask a question: streams an answer from the Anthropic API (via backend proxy).
 *
 * TODO: implement streaming answer rendering (currently waits for full response).
 * TODO: add citation links to referenced records in the answer.
 * TODO: surface EmbeddingJob status for admins so they can see indexing progress.
 */
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { aiApi }      from "@/api/ai";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button }     from "@/components/ui/Button";
import { Spinner }    from "@/components/ui/Spinner";
import type { SemanticSearchResult } from "@/types/ai";

// TODO: add types/ai.ts with SemanticSearchResult and AIAnswer types

type Mode = "search" | "ask";

export default function AIHubPage() {
  const [searchParams]          = useSearchParams();
  const [mode, setMode]         = useState<Mode>("search");
  const [query, setQuery]       = useState(() => searchParams.get("q") ?? "");
  const [loading, setLoading]   = useState(false);
  const [results, setResults]   = useState<SemanticSearchResult[]>([]);
  const [answer, setAnswer]     = useState<string | null>(null);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    const q = searchParams.get("q");
    if (q) setQuery(q);
  }, [searchParams]);

  const handleSubmit = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);
    setAnswer(null);

    try {
      if (mode === "search") {
        const { data } = await aiApi.semanticSearch(query);
        const payload = data as { results?: SemanticSearchResult[]; sources?: SemanticSearchResult[] };
        setResults(payload.results ?? payload.sources ?? []);
      } else {
        const { data } = await aiApi.ask(query);
        setAnswer(data.answer);
      }
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="AI Research Hub"
        description="Search research records by meaning or ask a question about the research corpus."
      />

      {/* Mode toggle */}
      <div className="flex gap-2 mb-5">
        <button
          onClick={() => { setMode("search"); setResults([]); setAnswer(null); }}
          className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-colors
            ${mode === "search"
              ? "bg-[#6B0F12] text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
        >
          <i className="fa fa-search mr-2" />
          Semantic Search
        </button>
        <button
          onClick={() => { setMode("ask"); setResults([]); setAnswer(null); }}
          className={`px-4 py-2 rounded-lg text-[13px] font-medium transition-colors
            ${mode === "ask"
              ? "bg-[#6B0F12] text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
        >
          <i className="fa fa-robot mr-2" />
          Ask a Question
        </button>
      </div>

      {/* Query input */}
      <div className="flex gap-3 mb-6">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          placeholder={
            mode === "search"
              ? "Describe the research you are looking for..."
              : "Ask a question about the research records..."
          }
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-[13px] outline-none
            focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12] text-gray-900
            placeholder:text-gray-400"
        />
        <Button onClick={handleSubmit} loading={loading} disabled={!query.trim()}>
          {mode === "search" ? "Search" : "Ask"}
        </Button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-[13px] text-red-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      )}

      {/* Semantic search results */}
      {!loading && mode === "search" && results.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-gray-400 uppercase tracking-wide font-semibold">
            {results.length} result{results.length !== 1 ? "s" : ""}
          </p>
          {results.map((r) => (
            <div key={r.id} className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/records/${r.id}`}
                    className="text-[14px] font-semibold text-[#6B0F12] hover:underline"
                  >
                    {r.title}
                  </Link>
                  {r.abstract && (
                    <p className="text-[13px] text-gray-600 mt-1 line-clamp-2">{r.abstract}</p>
                  )}
                  {r.authors && (
                    <p className="text-[12px] text-gray-400 mt-1">{r.authors}</p>
                  )}
                </div>
                {r.score !== undefined && (
                  <div className="shrink-0 text-right">
                    <span className="text-[11px] font-medium text-gray-500">
                      {(r.score * 100).toFixed(0)}% match
                    </span>
                    {/* Visual score bar */}
                    <div className="w-16 h-1.5 bg-gray-200 rounded-full mt-1 overflow-hidden">
                      <div
                        className="h-full bg-[#6B0F12] rounded-full"
                        style={{ width: `${Math.min(100, r.score * 100)}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* No results */}
      {!loading && mode === "search" && results.length === 0 && query && !error && !loading && (
        <div className="text-center py-12 text-gray-400 text-[13px]">
          No matching records found.
        </div>
      )}

      {/* Ask answer */}
      {!loading && mode === "ask" && answer && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-3">
            <i className="fa fa-robot text-[#6B0F12]" />
            <span className="text-[13px] font-semibold text-gray-700">AI Answer</span>
          </div>
          <div className="text-[13px] text-gray-800 leading-relaxed whitespace-pre-wrap">
            {answer}
          </div>
          <p className="text-[11px] text-gray-400 mt-4">
            AI answers are based on the research corpus and may contain inaccuracies. Always verify with the source records.
          </p>
        </div>
      )}
    </div>
  );
}
