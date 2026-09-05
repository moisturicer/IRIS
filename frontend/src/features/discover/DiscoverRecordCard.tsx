import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { RecordListItem } from "@/types/records";
import { PaperSaveDropdown } from "./PaperSaveDropdown";
import {
  CitationIcon,
  CommercialReadyIcon,
  IpProtectedIcon,
} from "./DiscoverIcons";
import {
  BADGE_TONE_CLASS,
  formatAuthorList,
  highlightMatch,
  isStarred,
  metaBadges,
  recordYearLabel,
  toggleStarred,
} from "./discoverUtils";
import type { BadgeIcon } from "./discoverUtils";
import { cn } from "@/lib/utils";

interface DiscoverRecordCardProps {
  record: RecordListItem;
  searchHighlight?: string;
  onCite: () => void;
}

const BADGE_ICONS: Record<BadgeIcon, (p: { className?: string }) => JSX.Element> = {
  ip:         IpProtectedIcon,
  commercial: CommercialReadyIcon,
  extension:  ({ className }) => <i className={cn("fas fa-people-group", className)} />,
};

export function DiscoverRecordCard({
  record,
  searchHighlight = "",
  onCite,
}: DiscoverRecordCardProps) {
  const navigate = useNavigate();
  const [starred, setStarred] = useState(() => isStarred(record.id));
  const [expanded, setExpanded] = useState(false);

  const badges = metaBadges(record);
  const abstract = record.abstract?.trim() ?? "";
  // Only offer to expand when there is meaningfully more than the clamp shows.
  const hasMoreToRead = abstract.length > 260;

  const [shared, setShared] = useState(false);

  const handleShare = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/records/${record.id}`);
      setShared(true);
      setTimeout(() => setShared(false), 2000);
    } catch {
      setShared(false);
    }
  };

  const handleStar = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setStarred(toggleStarred(record.id));
  };

  return (
    <article
      onClick={() => navigate(`/records/${record.id}`)}
      className="group bg-white rounded-xl border border-slate-200 hover:border-brand-200 hover:shadow-card transition-all cursor-pointer"
    >
      <div className="p-5">
        {/* Badge row — topic, kind, protection, programme flags */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex flex-wrap items-center gap-1.5 min-w-0">
            {badges.map((badge) => (
              <span
                key={badge.label}
                className={cn(
                  "px-2 py-0.5 rounded-md text-[11px] font-bold leading-5 flex items-center gap-1 whitespace-nowrap",
                  BADGE_TONE_CLASS[badge.tone],
                )}
              >
                {badge.icon &&
                  (() => {
                    const Icon = BADGE_ICONS[badge.icon];
                    return <Icon className="w-3 h-3 shrink-0" />;
                  })()}
                <span>{badge.label}</span>
              </span>
            ))}
          </div>

          <span className="text-[11px] font-medium text-slate-400 shrink-0 whitespace-nowrap">
            CIT-U {recordYearLabel(record)}
          </span>
        </div>

        {/* Title — the primary action on the card */}
        <h2 className="text-[17px] font-bold text-slate-900 leading-snug mb-1.5">
          <Link to={`/records/${record.id}`} className="hover:text-brand transition-colors">
            {highlightMatch(record.title, searchHighlight)}
          </Link>
        </h2>

        {/* Byline */}
        <p className={cn("flex items-start gap-1.5 text-[12px] text-brand font-medium mb-2.5", !expanded && "truncate")}>
          <i className="fas fa-user-group text-[10px] text-slate-300 mt-1 shrink-0" />
          <span className={cn(!expanded && "truncate")}>
            {highlightMatch(formatAuthorList(record.authors), searchHighlight)}
          </span>
        </p>

        {/* Abstract */}
        {abstract ? (
          <p className={cn("text-[13px] text-slate-600 leading-relaxed", !expanded && "line-clamp-3")}>
            {highlightMatch(abstract, searchHighlight)}
          </p>
        ) : (
          <p className="text-[13px] text-slate-400 italic">No abstract provided.</p>
        )}

        {hasMoreToRead && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setExpanded((v) => !v);
            }}
            className="mt-2 text-[12px] font-bold text-brand hover:underline flex items-center gap-1.5"
          >
            <i className={cn("fas text-[9px]", expanded ? "fa-chevron-up" : "fa-chevron-down")} />
            <span>{expanded ? "Show less" : "Quick read"}</span>
          </button>
        )}
      </div>

      {/* Footer — passive stats left, actions right */}
      <div className="px-5 py-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4 text-[12px] text-slate-400 font-medium">
          <span className="flex items-center gap-1.5" title="Times this record has been opened">
            <i className="fas fa-eye text-[11px]" />
            <span>{record.access_count} views</span>
          </span>
          <span className="flex items-center gap-1.5">
            <i className="fas fa-file-lines text-[11px]" />
            <span>
              {record.file_count} file{record.file_count === 1 ? "" : "s"}
            </span>
          </span>
          <span className="hidden sm:flex items-center gap-1.5">
            <i className="fas fa-calendar text-[11px]" />
            <span>{recordYearLabel(record)}</span>
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <IconButton
            icon={starred ? "fas fa-star" : "far fa-star"}
            label={starred ? "Starred" : "Star paper"}
            active={starred}
            onClick={handleStar}
          />
          <PaperSaveDropdown record={record} />
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onCite();
            }}
            title="Cite this paper"
            aria-label="Cite this paper"
            className="w-[30px] h-[30px] rounded-lg border border-slate-200 text-slate-400 hover:text-brand hover:border-brand-200 flex items-center justify-center transition-colors"
          >
            <CitationIcon className="w-[13px] h-[13px]" />
          </button>

          <IconButton
            icon={shared ? "fas fa-check" : "fas fa-share-nodes"}
            label={shared ? "Link copied" : "Copy link to record"}
            onClick={handleShare}
          />


        </div>
      </div>
    </article>
  );
}

/** Shared 30px outlined square used by every passive card action. */
function IconButton({
  icon,
  label,
  onClick,
  active = false,
}: {
  icon: string;
  label: string;
  onClick: (e: React.MouseEvent) => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cn(
        "w-[30px] h-[30px] rounded-lg border flex items-center justify-center transition-colors",
        active
          ? "border-amber-200 bg-amber-50 text-amber-500"
          : "border-slate-200 text-slate-400 hover:text-brand hover:border-brand-200",
      )}
    >
      <i className={cn(icon, "text-[12px]")} />
    </button>
  );
}
