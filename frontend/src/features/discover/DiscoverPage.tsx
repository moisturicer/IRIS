import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { Spinner } from "@/components/ui/Spinner";
import type { RecordListItem } from "@/types/records";
import {
  DISCOVER_QUICK_CHIPS,
  buildTrendingTopics,
  chipToSearchTerm,
  pickSpotlightAndRecent,
} from "@/lib/discoverUtils";
import { RecentIndexedRow, SearchResultCard, SpotlightCard } from "./DiscoverRecordCard";

export default function DiscoverPage() {
  const { logout } = useAuth();

  const [papers, setPapers] = useState<RecordListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [activeResults, setActiveResults] = useState<RecordListItem[] | null>(null);
  const [searching, setSearching] = useState(false);

  const loadPublished = useCallback(async (search?: string) => {
    setLoadError(null);
    const params: Record<string, unknown> = { ordering: "-created_at", page_size: 24 };
    if (search?.trim()) params.search = search.trim();
    const { data } = await recordsApi.list(params);
    return data.results ?? [];
  }, []);

  useEffect(() => {
    loadPublished()
      .then(setPapers)
      .catch(() => setLoadError("Could not load published records. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [loadPublished]);

  const handleSearch = async (queryStr: string) => {
    setSearchQuery(queryStr);
    if (!queryStr.trim()) {
      setActiveResults(null);
      return;
    }
    setSearching(true);
    try {
      const results = await loadPublished(queryStr);
      setActiveResults(results);
    } catch {
      setActiveResults([]);
    } finally {
      setSearching(false);
    }
  };

  const handleChipClick = (chip: string) => {
    handleSearch(chipToSearchTerm(chip));
  };

  const handleClearSearch = () => {
    setSearchQuery("");
    setActiveResults(null);
  };

  const handleSignOut = async () => {
    const refresh = useAuthStore.getState().refreshToken ?? "";
    await authApi.logout(refresh).catch(() => {});
    logout();
  };

  const { spotlight, recent } = pickSpotlightAndRecent(papers);
  const trendingTags = buildTrendingTopics(papers);

  return (
    <div className="-mx-4 sm:-mx-7 -mt-4 sm:-mt-7 flex flex-col min-h-[calc(100vh-58px)] bg-slate-50/50">
      {/* Discover sub-header (wireframe) */}
      <header className="px-6 sm:px-8 py-4 bg-white border-b border-slate-100 flex items-center justify-between shrink-0 sticky top-0 z-30">
        <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
          <Link to="/" className="hover:text-brand transition-colors">
            Home
          </Link>
          <span className="text-slate-300">/</span>
          <span className="text-slate-800 font-semibold">Discover</span>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSignOut}
            className="flex items-center gap-2 px-3 py-1.5 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 hover:text-slate-800 text-xs font-semibold transition"
          >
            <i className="fas fa-sign-out-alt text-[13px]" />
            <span className="hidden sm:inline">Sign Out</span>
          </button>
        </div>
      </header>

      <div className="p-6 sm:p-8 max-w-7xl mx-auto w-full space-y-8 flex-1">
        {/* Hero */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-tr from-[#611616] via-[#751d1d] to-[#942727] text-white px-6 sm:px-8 py-12 md:py-16 shadow-lg border border-[#802222]">
          <div
            className="absolute inset-0 opacity-10 pointer-events-none"
            style={{
              backgroundImage:
                "linear-gradient(to right, #808080 1px, transparent 1px), linear-gradient(to bottom, #808080 1px, transparent 1px)",
              backgroundSize: "14px 24px",
            }}
          />
          <div className="absolute right-0 top-0 w-96 h-96 bg-red-500/10 rounded-full blur-3xl pointer-events-none" />

          <div className="relative max-w-3xl mx-auto text-center flex flex-col items-center">
            <h1 className="text-2xl sm:text-4xl font-bold tracking-tight text-white leading-tight">
              Explore CIT-U&apos;s Institutional Knowledge Base
            </h1>
            <p className="mt-2 text-xs sm:text-sm text-red-200/90 font-medium tracking-wide uppercase">
              Powered by Retrieval-Augmented Generation (RAG)
            </p>

            <div className="mt-8 w-full max-w-2xl relative flex items-center bg-white rounded-full shadow-md p-1.5 border border-red-950/20 focus-within:ring-2 focus-within:ring-red-200 transition">
              <i className="fas fa-search text-slate-400 text-[14px] ml-3 shrink-0" />
              <input
                type="text"
                placeholder="Ask a research question, or search by keyword, author, or abstract..."
                value={searchQuery}
                onChange={(e) => {
                  const v = e.target.value;
                  setSearchQuery(v);
                  if (!v.trim()) setActiveResults(null);
                }}
                onKeyDown={(e) => e.key === "Enter" && handleSearch(searchQuery)}
                className="w-full pl-3 pr-24 py-2.5 text-sm text-slate-800 outline-none placeholder-slate-400 bg-transparent"
              />
              <button
                type="button"
                onClick={() => handleSearch(searchQuery)}
                disabled={searching}
                className="absolute right-1.5 px-5 py-2 bg-[#721c1c] text-white hover:bg-[#5b1616] disabled:opacity-70 rounded-full text-xs font-semibold tracking-wide shadow-sm transition-colors"
              >
                {searching ? "…" : "Search"}
              </button>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
              <span className="text-[11px] text-red-200/80 uppercase font-mono tracking-wider font-semibold mr-1">
                Suggested:
              </span>
              {DISCOVER_QUICK_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => handleChipClick(chip)}
                  className="px-3.5 py-1 text-xs font-medium rounded-full bg-red-900/40 text-red-100 hover:bg-white/10 hover:text-white transition-colors border border-red-100/10"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex justify-center py-20">
            <Spinner />
          </div>
        ) : loadError ? (
          <div className="text-center py-16 bg-white rounded-2xl border border-slate-100">
            <p className="text-sm text-red-600 font-medium">{loadError}</p>
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                loadPublished().then(setPapers).finally(() => setLoading(false));
              }}
              className="mt-4 text-xs font-semibold text-brand hover:underline"
            >
              Retry
            </button>
          </div>
        ) : activeResults !== null ? (
          <div className="space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h2 className="text-xl font-bold text-slate-800">Search Results</h2>
                <p className="text-xs text-slate-400 mt-1 font-mono">
                  Found {activeResults.length} matching records for &quot;{searchQuery}&quot;
                </p>
              </div>
              <button
                type="button"
                onClick={handleClearSearch}
                className="flex items-center gap-1 text-xs text-[#721c1c] font-semibold hover:underline"
              >
                <i className="fas fa-arrow-left text-[12px]" />
                Return to Discover
              </button>
            </div>

            {activeResults.length === 0 ? (
              <div className="text-center py-16 bg-white rounded-2xl border border-slate-100 shadow-sm">
                <i className="fas fa-search text-4xl text-slate-300 mb-3" />
                <h3 className="font-medium text-slate-700 text-base">No matches found</h3>
                <p className="text-xs text-slate-400 max-w-sm mx-auto mt-1">
                  Try different keywords, an author name, or a classification chip above.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {activeResults.map((record) => (
                  <SearchResultCard
                    key={record.id}
                    record={record}
                  />
                ))}
              </div>
            )}
          </div>
        ) : papers.length === 0 ? (
          <div className="text-center py-16 bg-white rounded-2xl border border-slate-100">
            <p className="text-sm text-slate-600">No published records yet.</p>
            <Link to="/records/add" className="mt-3 inline-block text-xs font-semibold text-brand hover:underline">
              Submit a disclosure
            </Link>
          </div>
        ) : (
          <div className="space-y-10">
            <section>
              <h2 className="text-lg font-bold text-slate-800 tracking-tight mb-4">
                Spotlight Research
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {spotlight.map((record, index) => (
                  <SpotlightCard
                    key={record.id}
                    record={record}
                    index={index}
                  />
                ))}
              </div>
            </section>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <section className="lg:col-span-2 space-y-4">
                <h2 className="text-lg font-bold text-slate-800 tracking-tight">
                  Recently Indexed
                </h2>
                <div className="space-y-4">
                  {recent.length === 0 ? (
                    <p className="text-xs text-slate-400">No additional records to show.</p>
                  ) : (
                    recent.map((record) => (
                      <RecentIndexedRow key={record.id} record={record} />
                    ))
                  )}
                </div>
              </section>

              <aside className="p-6 bg-white rounded-2xl border border-slate-100 shadow-sm h-fit space-y-4">
                <h2 className="text-sm font-bold text-slate-800 tracking-wider uppercase">
                  Trending Topics at CIT-U
                </h2>
                <div className="flex flex-col gap-2">
                  {trendingTags.map((tag) => (
                    <button
                      key={tag}
                      type="button"
                      onClick={() => handleSearch(tag)}
                      className="w-full text-left px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-700 border border-slate-100 bg-slate-50/50 hover:bg-red-50 hover:text-[#721c1c] hover:border-red-100 transition flex items-center gap-1.5"
                    >
                      <span className="text-[#721c1c] font-bold">#</span>
                      <span className="truncate">{tag}</span>
                    </button>
                  ))}
                </div>
              </aside>
            </div>
            {/* Research Analytics — Coming Soon */}
            <section>
              <div className="flex items-center gap-3 mb-4">
                <h2 className="text-lg font-bold text-slate-800 tracking-tight">
                  Research Analytics
                </h2>
                <span className="px-2.5 py-0.5 bg-amber-50 text-amber-700 text-[10px] font-bold rounded-full border border-amber-200 uppercase tracking-wider">
                  Coming Soon
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Classification Distribution placeholder */}
                <div className="relative bg-white rounded-2xl border border-slate-100 shadow-sm p-6 min-h-[180px] flex flex-col justify-between overflow-hidden">
                  <p className="text-[12px] font-semibold text-slate-400 mb-3">
                    Classification Distribution
                  </p>
                  <div className="flex items-end gap-1.5 h-20 opacity-20">
                    {[55, 80, 40, 95, 65, 50, 75, 45].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-slate-200 rounded-t"
                        style={{ height: `${h}%` }}
                      />
                    ))}
                  </div>
                  <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/75 backdrop-blur-[1px]">
                    <i className="fas fa-chart-bar text-2xl text-slate-200 mb-2" />
                    <span className="text-[12px] text-slate-400 font-medium">In development</span>
                  </div>
                </div>

                {/* PSCED Distribution placeholder */}
                <div className="relative bg-white rounded-2xl border border-slate-100 shadow-sm p-6 min-h-[180px] flex flex-col justify-between overflow-hidden">
                  <p className="text-[12px] font-semibold text-slate-400 mb-3">
                    PSCED Field Distribution
                  </p>
                  <div className="space-y-2 opacity-20">
                    {[75, 55, 90, 40, 65].map((w, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <div className="h-3 bg-slate-200 rounded-full" style={{ width: `${w}%` }} />
                      </div>
                    ))}
                  </div>
                  <div className="absolute inset-0 flex flex-col items-center justify-center bg-white/75 backdrop-blur-[1px]">
                    <i className="fas fa-chart-pie text-2xl text-slate-200 mb-2" />
                    <span className="text-[12px] text-slate-400 font-medium">In development</span>
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
