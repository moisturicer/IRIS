import { Link } from "react-router-dom";
import type { RecordListItem } from "@/types/records";
import type { SpotlightBadge } from "@/lib/discoverUtils";
import {
  formatAuthorList,
  listBadges,
  recordCollegeLabel,
  recordPubLabel,
  spotlightBadges,
} from "@/lib/discoverUtils";
import { cn } from "@/lib/utils";

const BADGE_STYLES: Record<SpotlightBadge["tone"], string> = {
  award:  "bg-amber-50 text-amber-700 border-amber-100",
  patent: "bg-blue-50 text-blue-700 border-blue-100",
  faculty:"bg-emerald-50 text-emerald-700 border-emerald-100",
};

interface SpotlightCardProps {
  record: RecordListItem;
  index: number;
}

export function SpotlightCard({ record, index }: SpotlightCardProps) {
  const badges = spotlightBadges(record, index);
  const excerpt = record.abstract?.trim()
    ? `"${record.abstract.slice(0, 220)}${record.abstract.length > 220 ? "…" : ""}"`
    : "No abstract available for this record.";

  return (
    <div className="p-6 bg-white rounded-2xl border border-slate-100 shadow-sm hover:shadow-md transition flex flex-col justify-between min-h-[280px]">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          {badges.map((b) => (
            <span
              key={b.label}
              className={cn(
                "flex items-center gap-1 px-3 py-1.5 rounded-full text-[10px] font-bold border select-none",
                BADGE_STYLES[b.tone]
              )}
            >
              {b.tone === "award" && <i className="fas fa-trophy text-[10px] text-amber-500" />}
              {b.tone === "patent" && <i className="fas fa-book text-[10px] text-blue-600" />}
              {b.tone === "faculty" && <i className="fas fa-star text-[10px] text-emerald-600" />}
              {b.label}
            </span>
          ))}
        </div>
        <Link
          to={`/records/${record.id}`}
          className="block text-lg sm:text-xl font-bold text-slate-800 hover:text-[#721c1c] transition-colors mt-3 tracking-tight"
        >
          {record.title}
        </Link>
        <p className="text-slate-500 text-xs font-semibold mt-1">{formatAuthorList(record.authors)}</p>
        <p className="text-slate-500 text-xs sm:text-sm mt-4 leading-relaxed">{excerpt}</p>
      </div>
      <div className="mt-8 pt-4 border-t border-slate-50 flex flex-wrap items-center gap-3">
        <Link
          to={`/records/${record.id}`}
          className="px-5 py-2.5 bg-[#721c1c] text-white hover:bg-[#5b1616] rounded-xl text-xs font-bold tracking-wide transition shadow-sm"
        >
          Read Full Text
        </Link>
        <span className="flex items-center gap-1.5 px-5 py-2.5 border border-slate-100 text-slate-400 rounded-xl text-xs font-bold tracking-wide cursor-default select-none">
          <i className="fas fa-magic text-slate-300 text-[12px]" />
          Summarize with AI
          <span className="px-1.5 py-0.5 bg-amber-50 text-amber-500 text-[9px] font-bold rounded-full border border-amber-100 uppercase tracking-wider leading-none">
            soon
          </span>
        </span>
      </div>
    </div>
  );
}

interface RecentRowProps {
  record: RecordListItem;
}

export function RecentIndexedRow({ record }: RecentRowProps) {
  const badges = listBadges(record);
  return (
    <Link
      to={`/records/${record.id}`}
      className="group p-5 bg-white rounded-2xl border border-slate-100 shadow-sm hover:border-[#721c1c]/20 hover:shadow-md transition flex items-start justify-between gap-4"
    >
      <div className="space-y-1 min-w-0">
        <h4 className="text-blue-600 group-hover:underline text-sm font-semibold tracking-tight leading-snug">
          {record.title}
        </h4>
        <p className="text-slate-400 font-mono text-[11px]">
          {recordCollegeLabel(record)} • {recordPubLabel(record)}
        </p>
        <div className="flex flex-wrap gap-1 pt-1.5">
          {badges.map((b) => (
            <span
              key={b}
              className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600"
            >
              {b}
            </span>
          ))}
        </div>
      </div>
      <span className="p-1.5 rounded-lg bg-slate-50 text-slate-400 opacity-0 group-hover:opacity-100 group-hover:bg-red-50 group-hover:text-[#721c1c] transition shrink-0">
        <i className="fas fa-arrow-right text-[12px]" />
      </span>
    </Link>
  );
}

interface SearchResultCardProps {
  record: RecordListItem;
}

export function SearchResultCard({ record }: SearchResultCardProps) {
  const tags = listBadges(record);
  return (
    <div className="p-6 bg-white rounded-2xl border border-slate-100 shadow-sm hover:shadow-md transition flex flex-col justify-between">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-[10px] font-mono tracking-widest text-[#721c1c] uppercase font-bold">
            {recordCollegeLabel(record)}
          </span>
          <div className="flex gap-1">
            {tags.slice(0, 2).map((t) => (
              <span
                key={t}
                className="text-[9px] font-mono border border-slate-100 px-2 py-0.5 rounded-full text-slate-500 bg-slate-50"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
        <Link
          to={`/records/${record.id}`}
          className="block text-base font-bold text-slate-800 hover:text-[#721c1c] transition-colors mt-2"
        >
          {record.title}
        </Link>
        <p className="text-[11px] text-slate-400 font-semibold mt-1">
          {formatAuthorList(record.authors)} • {recordPubLabel(record)}
        </p>
        <p className="text-slate-500 text-xs mt-3 line-clamp-3">
          {record.abstract || "No abstract available."}
        </p>
      </div>
      <div className="mt-5 pt-4 border-t border-slate-50 flex items-center justify-end gap-2">
        <span className="flex items-center gap-1 px-3 py-1.5 border border-slate-100 text-slate-400 rounded-lg text-xs font-semibold cursor-default select-none">
          <i className="fas fa-magic text-slate-300 text-[11px]" />
          Summarize
          <span className="px-1.5 py-0.5 bg-amber-50 text-amber-500 text-[9px] font-bold rounded-full border border-amber-100 uppercase tracking-wider leading-none">
            soon
          </span>
        </span>
        <Link
          to={`/records/${record.id}`}
          className="px-3.5 py-1.5 bg-[#721c1c] text-white rounded-lg hover:bg-[#5f1717] text-xs font-semibold transition"
        >
          Read Paper
        </Link>
      </div>
    </div>
  );
}
