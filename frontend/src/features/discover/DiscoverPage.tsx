import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { dashboardApi } from "@/api/dashboard";
import type { Classification, RecordListItem } from "@/types/records";
import type { ClassificationChartRow } from "@/api/dashboard";
import { EmptyState } from "@/components/shared/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { useDiscoverSearch } from "@/contexts/DiscoverSearchContext";
import {
  classificationToHashtag,
  formatAuthors,
  getSpotlightBadges,
  truncateText,
} from "./discoverUtils";

interface DiscoverFilters {
  classification?: number;
  is_ip?:          boolean;
  year_from?:      number;
}

const TRENDING_COLORS = [
  "text-brand",
  "text-gray-800",
  "text-blue-700",
  "text-gray-700",
  "text-emerald-700",
];

function Breadcrumbs() {
  return (
    <nav className="text-[12px] text-gray-500 mb-5" aria-label="Breadcrumb">
      <Link to="/" className="hover:text-brand">Home</Link>
      <span className="mx-1.5">/</span>
      <span className="text-gray-800 font-medium">Discover</span>
    </nav>
  );
}

function RecordBadges({ badges }: { badges: ReturnType<typeof getSpotlightBadges> }) {
  return (
    <div className="flex flex-wrap gap-2">
      {badges.map((badge) => (
        <span
          key={badge.label}
          className={`inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold ${badge.className}`}
        >
          {badge.label}
        </span>
      ))}
    </div>
  );
}

function SpotlightCard({ record }: { record: RecordListItem }) {
  const badges = getSpotlightBadges(record);

  return (
    <article className="bg-white rounded-2xl border border-gray-200 p-6 flex flex-col h-full hover:shadow-card-md transition-shadow">
      <RecordBadges badges={badges} />
      <h3 className="text-[17px] font-bold text-gray-900 mt-4 leading-snug">{record.title}</h3>
      <p className="text-[12px] text-gray-500 mt-2">{formatAuthors(record)}</p>
      <p className="text-[13px] text-gray-600 mt-3 leading-relaxed flex-1">
        {truncateText(record.abstract || "No abstract available.")}
      </p>
      <div className="flex flex-wrap gap-2 mt-5 pt-4 border-t border-gray-100">
        <Link
          to={`/records/${record.id}`}
          className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-brand text-white text-[12px] font-semibold hover:bg-brand-dark transition-colors"
        >
          Read Full Text
        </Link>
        <Link
          to={`/ai?q=${encodeURIComponent(record.title)}`}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-gray-300 bg-white text-[12px] font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <i className="fa-solid fa-wand-magic-sparkles text-[11px] text-brand" aria-hidden />
          Summarize with AI
        </Link>
      </div>
    </article>
  );
}

function LoadingBlock() {
  return (
    <div className="flex justify-center py-12">
      <Spinner />
    </div>
  );
}

function RecordTags({ record }: { record: RecordListItem }) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {record.record_type_name && (
        <span className="px-2.5 py-0.5 rounded-full bg-gray-100 text-[11px] font-medium text-gray-600">
          {record.record_type_name}
        </span>
      )}
      {record.classification_name && (
        <span className="px-2.5 py-0.5 rounded-full bg-gray-100 text-[11px] font-medium text-gray-600">
          {record.classification_name}
        </span>
      )}
    </div>
  );
}

function RecentlyIndexed({ loading, recent }: { loading: boolean; recent: RecordListItem[] }) {
  return (
    <section className="lg:col-span-2">
      <h2 className="text-[18px] font-bold text-gray-900 mb-4">Recently Indexed</h2>
      {loading ? (
        <LoadingBlock />
      ) : recent.length === 0 ? (
        <EmptyState title="No recent records" message="Newly published research will show up here." />
      ) : (
        <ul className="space-y-4">
          {recent.map((record) => (
            <li
              key={record.id}
              className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow"
            >
              <Link
                to={`/records/${record.id}`}
                className="text-[15px] font-semibold text-blue-700 hover:underline leading-snug"
              >
                {record.title}
              </Link>
              <p className="text-[12px] text-gray-500 mt-1.5">
                {record.classification_name ?? "Uncategorized"}
                {" â€¢ "}
                Published: {formatDate(record.created_at, "MMM yyyy")}
              </p>
              <RecordTags record={record} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TrendingSidebar({ trending }: { trending: ClassificationChartRow[] }) {
  return (
    <section>
      <h2 className="text-[18px] font-bold text-gray-900 mb-4">Trending Topics at CIT-U</h2>
      {trending.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <p className="text-[13px] text-gray-500">
            Trending topics will appear as more research is published.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex flex-wrap gap-x-3 gap-y-3">
            {trending.slice(0, 8).map((row, i) => (
              <Link
                key={row.classification__name}
                to={`/records?search=${encodeURIComponent(row.classification__name ?? "")}`}
                className={`text-[14px] font-semibold hover:underline ${TRENDING_COLORS[i % TRENDING_COLORS.length]}`}
              >
                {classificationToHashtag(row.classification__name!)}
              </Link>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default function DiscoverPage() {
  const navigate = useNavigate();
  const { registerHeroSearch } = useDiscoverSearch();
  const currentYear = new Date().getFullYear();

  const [query, setQuery]                     = useState("");
  const [filters, setFilters]                 = useState<DiscoverFilters>({});
  const [spotlight, setSpotlight]             = useState<RecordListItem[]>([]);
  const [recent, setRecent]                   = useState<RecordListItem[]>([]);
  const [classifications, setClassifications] = useState<Classification[]>([]);
  const [trending, setTrending]               = useState<ClassificationChartRow[]>([]);
  const [loading, setLoading]                 = useState(true);
  const [error, setError]                     = useState<string | null>(null);

  const listParams = useMemo(
    () => ({
      ...(filters.classification ? { classification: filters.classification } : {}),
      ...(filters.is_ip != null ? { is_ip: filters.is_ip } : {}),
      ...(filters.year_from ? { year_from: filters.year_from } : {}),
    }),
    [filters]
  );

  const hasActiveFilters = Boolean(
    filters.classification || filters.is_ip || filters.year_from
  );

  const loadDiscover = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [spotlightRes, recentRes, classRes, trendRes] = await Promise.all([
        recordsApi.list({ ...listParams, ordering: "-access_count", page_size: 2 }),
        recordsApi.list({ ...listParams, ordering: "-created_at", page_size: 5 }),
        recordsApi.classifications(),
        dashboardApi.classifications(),
      ]);
      setSpotlight(spotlightRes.data.results);
      setRecent(recentRes.data.results);
      setClassifications(classRes.data.results ?? []);
      setTrending(trendRes.data.filter((row) => row.classification__name && row.count > 0));
    } catch {
      setError("Unable to load discovery content. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [listParams]);

  useEffect(() => {
    loadDiscover();
  }, [loadDiscover]);

  const quickChips = useMemo(() => {
    const chips: { label: string; onClick: () => void; active: boolean }[] = [];

    classifications.slice(0, 2).forEach((c) => {
      chips.push({
        label: c.name,
        active: filters.classification === c.id,
        onClick: () =>
          setFilters((prev) => ({
            classification: prev.classification === c.id ? undefined : c.id,
            is_ip: undefined,
            year_from: undefined,
          })),
      });
    });

    chips.push({
      label: "Patents",
      active: filters.is_ip === true,
      onClick: () =>
        setFilters((prev) => ({
          is_ip: prev.is_ip ? undefined : true,
          classification: undefined,
          year_from: undefined,
        })),
    });

    chips.push({
      label: `Recent ${currentYear}`,
      active: filters.year_from === currentYear,
      onClick: () =>
        setFilters((prev) => ({
          year_from: prev.year_from === currentYear ? undefined : currentYear,
          classification: undefined,
          is_ip: undefined,
        })),
    });

    return chips;
  }, [classifications, currentYear, filters]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    navigate(`/ai?q=${encodeURIComponent(trimmed)}`);
  };

  if (loading && spotlight.length === 0 && recent.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[320px]">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="w-full">
      <Breadcrumbs />

      <section
        ref={registerHeroSearch}
        className="w-full rounded-2xl bg-brand px-6 sm:px-10 py-10 text-white shadow-card-md text-center mb-8"
      >
        <div className="mx-auto max-w-3xl">
          <h1 className="text-[26px] sm:text-[30px] font-bold leading-tight">
            Explore CIT-U&apos;s Institutional Knowledge Base
          </h1>
          <p className="text-[14px] text-white/80 mt-2">
            Powered by Retrieval-Augmented Generation (RAG)
          </p>

          <form onSubmit={handleSearch} className="mt-6 relative text-left">
            <i
              className="fa-solid fa-magnifying-glass absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-[14px]"
              aria-hidden
            />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a research question, or search by keyword, author, or abstract..."
              className="w-full pl-11 pr-28 py-3.5 rounded-xl text-[14px] text-gray-900 bg-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-white/40"
            />
            <button
              type="submit"
              className="absolute right-2 top-1/2 -translate-y-1/2 px-5 py-2 rounded-lg bg-brand-dark text-white text-[13px] font-semibold hover:bg-brand transition-colors border border-white/20"
            >
              Search
            </button>
          </form>

          <div className="flex flex-wrap justify-center gap-2 mt-4">
            {quickChips.map((chip) => (
              <button
                key={chip.label}
                type="button"
                onClick={chip.onClick}
                className={`px-3.5 py-1.5 rounded-full text-[12px] font-medium transition-colors ${
                  chip.active
                    ? "bg-white text-brand"
                    : "bg-white/15 text-white hover:bg-white/25"
                }`}
              >
                {chip.label}
              </button>
            ))}
            {hasActiveFilters && (
              <button
                type="button"
                onClick={() => setFilters({})}
                className="px-3.5 py-1.5 rounded-full text-[12px] font-medium text-white/80 hover:text-white underline"
              >
                Clear filters
              </button>
            )}
          </div>
        </div>
      </section>

      {error && (
        <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          {error}
        </div>
      )}

      <section className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-[18px] font-bold text-gray-900">Spotlight Research</h2>
          <Link to="/records" className="text-[12px] font-semibold text-brand hover:underline">
            Browse all
          </Link>
        </div>
        {loading ? (
          <LoadingBlock />
        ) : spotlight.length === 0 ? (
          <EmptyState
            title="No spotlight records yet"
            message="Published research with high engagement will appear here."
          />
        ) : (
          <div className="grid md:grid-cols-2 gap-5">
            {spotlight.map((record) => (
              <SpotlightCard key={record.id} record={record} />
            ))}
          </div>
        )}
      </section>

      <div className="grid lg:grid-cols-3 gap-6">
        <RecentlyIndexed loading={loading} recent={recent} />
        <TrendingSidebar trending={trending} />
      </div>
    </div>
  );
}
