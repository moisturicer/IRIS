import { useState } from "react";

import { ResearchCard } from "@/components/shared/ResearchCard";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { RecordListItem } from "@/types/records";
import { CitationIcon } from "./DiscoverIcons";
import { PaperSaveDropdown } from "./PaperSaveDropdown";
import {
  formatAuthorList,
  highlightMatch,
  ipTypeLabel,
  isStarred,
  recordYearLabel,
  toggleStarred,
} from "./discoverUtils";

interface DiscoverResultCardProps {
  record:          RecordListItem;
  searchHighlight: string;
  onCite:          () => void;
}

/**
 * A Discover result: `ResearchCard` filled from the list payload (IR-407,
 * spec §4.3 and §4.12).
 *
 * It shows only what `RecordListItem` carries. The list payload has no college,
 * so the card names none rather than guessing one; citation and download
 * counts do not exist, so views are the only figure.
 */
export function DiscoverResultCard({ record, searchHighlight, onCite }: DiscoverResultCardProps) {
  const [starred, setStarred] = useState(() => isStarred(record.id));
  const abstract = record.abstract?.trim() ?? "";

  const flags = [
    record.is_ip && { key: "ip", icon: "fa-shield-halved", label: ipTypeLabel(record.ip_type) },
    record.for_commercialization && { key: "commercial", icon: "fa-store", label: "Commercialization" },
    record.community_extension && { key: "extension", icon: "fa-people-group", label: "Community extension" },
  ].filter(Boolean) as { key: string; icon: string; label: string }[];

  return (
    <ResearchCard
      layout="grid"
      href={`/records/${record.id}`}
      title={record.title}
      eyebrow={
        <span className="flex flex-wrap items-center gap-x-1.5">
          {record.classification_name && <span className="text-brand">{record.classification_name}</span>}
          {record.classification_name && record.record_type_name && (
            <span aria-hidden="true" className="text-stone-400">·</span>
          )}
          {record.record_type_name && <span>{record.record_type_name}</span>}
        </span>
      }
      meta={recordYearLabel(record)}
      byline={highlightMatch(formatAuthorList(record.authors), searchHighlight)}
      summary={
        abstract ? highlightMatch(abstract, searchHighlight) : <span className="italic">No abstract provided.</span>
      }
      footer={
        <>
          <span className="inline-flex items-center gap-1.5" title="Times this record has been opened">
            <i className="fas fa-eye text-[12px] text-stone-500" aria-hidden />
            {record.access_count} {record.access_count === 1 ? "view" : "views"}
          </span>
          {flags.map((flag) => (
            <span key={flag.key} className="inline-flex items-center gap-1.5 text-stone-800">
              <i className={cn("fas text-[12px] text-brand", flag.icon)} aria-hidden />
              <span>{flag.label}</span>
            </span>
          ))}
        </>
      }
      actions={
        <>
          <button
            type="button"
            onClick={() => setStarred(toggleStarred(record.id))}
            aria-pressed={starred}
            aria-label={starred ? "Starred" : "Star paper"}
            title={starred ? "Starred" : "Star paper"}
            className={cn(
              "w-9 h-9 rounded-lg border flex items-center justify-center",
              COLOUR_TRANSITION,
              FOCUS_RING,
              starred
                ? "border-brand-100 bg-brand-50 text-brand"
                : "border-stone-200 text-stone-600 hover:text-brand hover:border-stone-400",
            )}
          >
            <i className={cn(starred ? "fas" : "far", "fa-star text-[13px]")} aria-hidden />
          </button>
          <PaperSaveDropdown record={record} />
          <button
            type="button"
            onClick={onCite}
            aria-label="Cite this paper"
            title="Cite this paper"
            className={cn(
              "w-9 h-9 rounded-lg border border-stone-200 text-stone-600 hover:text-brand hover:border-stone-400 flex items-center justify-center",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <CitationIcon className="w-[13px] h-[13px]" />
          </button>
        </>
      }
    />
  );
}
