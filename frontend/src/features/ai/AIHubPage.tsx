/**
 * Semantic search over the research corpus (companion to FR-M3-01 RAG chat at /ai).
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { aiApi } from "@/api/ai";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import type { SemanticSearchResult } from "@/types/ai";

export default function AIHubPage() {
  const [query, setQuery]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [results, setResults]   = useState<SemanticSearchResult[]>([]);
  const [error, setError]       = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);

    try {
      const { data } = await aiApi.semanticSearch(query);
      setResults(data.results ?? data.sources ?? []);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Semantic Search"
        description="Find research records by meaning, not just keywords."
        actions={
          <Link
            to="/ai"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#6B0F12] text-white text-[13px] font-semibold hover:bg-[#7d1215]"
          >
            <i className="fas fa-comments text-[12px]" />
            Open chat
          </Link>
        }
      />

      <div className="flex gap-3 mb-6">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
          placeholder="Describe the research you are looking for..."
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-[13px] outline-none
            focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12] text-gray-900 placeholder:text-gray-400"
        />
        <Button onClick={handleSubmit} loading={loading} disabled={!query.trim()}>
          Search
        </Button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-[13px] text-red-700">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      )}

      {!loading && results.length > 0 && (
        <div className="flex flex-col gap-3">
          <p className="text-[12px] text-gray-400 uppercase tracking-wide font-semibold">
            {results.length} result{results.length !== 1 ? "s" : ""}
          </p>
          {results.map((r) => (
            <div
              key={r.id}
              className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-sm transition-shadow"
            >
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

      {!loading && results.length === 0 && query && !error && (
        <div className="text-center py-12 text-gray-400 text-[13px]">
          No matching records found.
        </div>
      )}
    </div>
  );
}
