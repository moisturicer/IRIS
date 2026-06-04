import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader }  from "@/components/layout/PageHeader";
import { EmptyState }  from "@/components/shared/EmptyState";
import type { RecordListItem, Classification, RecordType } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";
import { formatDate } from "@/lib/utils";

// ---- Types -----------------------------------------------------------------

interface Filters {
  search:      string;
  year_from:   string;
  year_to:     string;
  record_type: string;   // ID string or ""
  classification: string;// ID string or ""
  ip_type:     string;   // "" | "patent" | "copyright" | "trade_secret" | "utility_model"
  is_ip:       string;   // "" | "true"
}

const EMPTY_FILTERS: Filters = {
  search: "", year_from: "", year_to: "",
  record_type: "", classification: "", ip_type: "", is_ip: "",
};

// ---- Helpers ---------------------------------------------------------------

function filtersToParams(f: Filters, page: number): Record<string, unknown> {
  const p: Record<string, unknown> = { page, ordering: "-created_at" };
  if (f.search)       p.search        = f.search;
  if (f.year_from)    p.year_from     = f.year_from;
  if (f.year_to)      p.year_to       = f.year_to;
  if (f.record_type)  p.record_type   = f.record_type;
  if (f.classification) p.classification = f.classification;
  if (f.ip_type)      p.ip_type       = f.ip_type;
  if (f.is_ip)        p.is_ip         = f.is_ip;
  return p;
}

function activeFilterCount(f: Filters): number {
  return Object.entries(f).filter(([k, v]) => k !== "search" && v !== "").length;
}

// ---- Component -------------------------------------------------------------

export default function PublishedRecordsPage() {
  const [filters,      setFilters]      = useState<Filters>(EMPTY_FILTERS);
  const [page,         setPage]         = useState(1);
  const [records,      setRecords]      = useState<RecordListItem[]>([]);
  const [total,        setTotal]        = useState(0);
  const [loading,      setLoading]      = useState(true);
  const [showFilters,  setShowFilters]  = useState(false);

  // Reference data for dropdowns
  const [classifications, setClassifications] = useState<Classification[]>([]);
  const [recordTypes,     setRecordTypes]     = useState<RecordType[]>([]);

  // Load reference data once
  useEffect(() => {
    recordsApi.classifications().then(({ data }) => setClassifications(data.results ?? [])).catch(() => {});
    recordsApi.recordTypes().then(({ data }) => setRecordTypes(data.results ?? [])).catch(() => {});
  }, []);

  // Fetch records whenever filters or page change
  useEffect(() => {
    setLoading(true);
    recordsApi.list(filtersToParams(filters, page))
      .then(({ data }) => { setRecords(data.results); setTotal(data.count); })
      .catch(() => {})
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters), page]);

  const updateFilter = useCallback(<K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  }, []);

  const clearFilters = () => { setFilters(EMPTY_FILTERS); setPage(1); };

  const activeCount = activeFilterCount(filters);
  const PAGE_SIZE   = 20;

  return (
    <div>
      <PageHeader title="Browse Collections" description="All published research records." />

      {/* Search + Filter toggle bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 space-y-3">
        <div className="flex gap-3">
          <input
            type="text"
            value={filters.search}
            placeholder="Search by title, author, abstract…"
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-[#6B0F12]"
            onChange={(e) => updateFilter("search", e.target.value)}
          />
          <button
            type="button"
            onClick={() => setShowFilters((v) => !v)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-[13px] font-medium transition-colors ${
              showFilters || activeCount > 0
                ? "border-[#6B0F12] text-[#6B0F12] bg-red-50"
                : "border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            <i className="fas fa-sliders-h text-[12px]" />
            Filters
            {activeCount > 0 && (
              <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-[#6B0F12] text-white text-[10px] font-bold flex items-center justify-center">
                {activeCount}
              </span>
            )}
          </button>
        </div>

        {/* Collapsible filter grid */}
        {showFilters && (
          <div className="border-t border-gray-100 pt-3 grid grid-cols-2 md:grid-cols-3 gap-3">
            {/* Year from / to */}
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Year (from)
              </label>
              <input
                type="number"
                value={filters.year_from}
                placeholder="e.g. 2020"
                min={1990}
                max={new Date().getFullYear()}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-[#6B0F12]"
                onChange={(e) => updateFilter("year_from", e.target.value)}
              />
            </div>

            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Year (to)
              </label>
              <input
                type="number"
                value={filters.year_to}
                placeholder="e.g. 2024"
                min={1990}
                max={new Date().getFullYear()}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-[#6B0F12]"
                onChange={(e) => updateFilter("year_to", e.target.value)}
              />
            </div>

            {/* Record type */}
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Record Type
              </label>
              <select
                value={filters.record_type}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-[#6B0F12] bg-white"
                onChange={(e) => updateFilter("record_type", e.target.value)}
              >
                <option value="">All types</option>
                {recordTypes.map((rt) => (
                  <option key={rt.id} value={String(rt.id)}>{rt.name}</option>
                ))}
              </select>
            </div>

            {/* Classification */}
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Classification
              </label>
              <select
                value={filters.classification}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-[#6B0F12] bg-white"
                onChange={(e) => updateFilter("classification", e.target.value)}
              >
                <option value="">All classifications</option>
                {classifications.map((c) => (
                  <option key={c.id} value={String(c.id)}>{c.name}</option>
                ))}
              </select>
            </div>

            {/* IP type */}
            <div>
              <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">
                IP Classification
              </label>
              <select
                value={filters.ip_type}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-[#6B0F12] bg-white"
                onChange={(e) => updateFilter("ip_type", e.target.value)}
              >
                <option value="">Any</option>
                {Object.entries(IP_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>

            {/* Is IP flag */}
            <div className="flex flex-col justify-end">
              <label className="flex items-center gap-2 cursor-pointer py-2">
                <input
                  type="checkbox"
                  checked={filters.is_ip === "true"}
                  className="accent-[#6B0F12] w-4 h-4"
                  onChange={(e) => updateFilter("is_ip", e.target.checked ? "true" : "")}
                />
                <span className="text-[13px] text-gray-700 font-medium">
                  Intellectual Property only
                </span>
              </label>
            </div>

            {/* Clear */}
            {activeCount > 0 && (
              <div className="col-span-full flex justify-end">
                <button
                  type="button"
                  onClick={clearFilters}
                  className="text-[12px] text-[#6B0F12] hover:underline"
                >
                  <i className="fas fa-times-circle mr-1" />
                  Clear all filters
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Results table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-[13px]">Loading…</div>
        ) : records.length === 0 ? (
          <EmptyState title="No records found" message="Try adjusting your search or filters." />
        ) : (
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Title</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Year</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Type</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Classification</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Date Added</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link to={`/records/${r.id}`} className="text-[#6B0F12] font-medium hover:underline">
                      {r.title}
                    </Link>
                    <div className="flex gap-1 mt-0.5 flex-wrap">
                      {r.is_ip && (
                        <span className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded text-[10px] font-semibold">IP</span>
                      )}
                      {r.ip_type && (
                        <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 rounded text-[10px] font-semibold">
                          {IP_TYPE_LABELS[r.ip_type as Exclude<typeof r.ip_type, "">]}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{r.year_accomplished ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{r.record_type_name ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{r.classification_name ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        <div className="px-4 py-3 flex items-center justify-between text-[12px] text-gray-500 border-t border-gray-100">
          <span>Showing {records.length} of {total}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-2 py-1 border rounded disabled:opacity-40"
            >
              Prev
            </button>
            <span className="px-2 py-1 text-gray-600">Page {page}</span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={records.length < PAGE_SIZE}
              className="px-2 py-1 border rounded disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
