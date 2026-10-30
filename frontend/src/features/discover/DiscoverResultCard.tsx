import { useState } from "react";

import { ResearchCard } from "@/components/shared/ResearchCard";
import { ResearchOriginBadge } from "@/components/shared/ResearchOriginBadge";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { ForYouItem, RecordListItem } from "@/types/records";
import { CitationIcon } from "./DiscoverIcons";
import { ManuscriptCover } from "./ManuscriptCover";
import { PaperSaveDropdown } from "./PaperSaveDropdown";
import {
  cardHook,
  formatAuthorList,
  highlightMatch,
  ipTypeLabel,
  isStarred,
  indexedOnLabel,
  recordYearLabel,
  toggleStarred,
} from "./discoverUtils";

interface DiscoverResultCardProps {
  record:          RecordListItem;
  searchHighlight: string;
  onCite:          () => void;
  reason?:         ForYouItem["reason"];
  expanded?:       boolean;
  /** For you only: hide this recommendation for the reader's account (IR-576). */
  onNotInterested?: () => void;
}

/**
 * A Discover result: `ResearchCard` filled from the list payload (IR-407,
 * spec §4.3 and §4.12).
 *
 * It shows only what `RecordListItem` carries. The list payload has no college,
 * so the card names none rather than guessing one; citation and download
 * counts do not exist, so views are the only figure.
 */
export function DiscoverResultCard({ record, searchHighlight, onCite, reason, expanded = false, onNotInterested }: DiscoverResultCardProps) {
  const [starred, setStarred] = useState(() => isStarred(record.id));
  const abstract = record.abstract?.trim() ?? "";
  const hook = cardHook({ abstract, ai_hook: record.ai_hook });

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
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          {record.classification_name && <span className="text-brand">{record.classification_name}</span>}
          {record.classification_name && record.record_type_name && (
            <span aria-hidden="true" className="text-stone-400">·</span>
          )}
          {record.record_type_name && <span>{record.record_type_name}</span>}
          {reason && <span aria-label="Why this was suggested" className="inline-flex rounded-md bg-stone-100 px-1.5 py-0.5 text-[11px] font-medium text-stone-700">
            {reason.kind === "selected_area" && reason.area
              ? `Because you chose ${reason.area}`
              : "Latest research"}
          </span>}
        </span>
      }
      meta={record.publication_year ? `Published ${recordYearLabel(record)}` : indexedOnLabel(record)}
      byline={formatAuthorList(record.authors) === "Authors not recorded"
        ? <span className="italic text-stone-500">Authors not recorded</span>
        : highlightMatch(formatAuthorList(record.authors), searchHighlight)}
      summary={abstract ? highlightMatch(abstract, searchHighlight) : <span className="italic">No abstract provided.</span>}
      summaryClassName={expanded ? "xl:line-clamp-5" : undefined}
      splitFooter={expanded}
      previewLabel="Manuscript and abstract preview"
      preview={expanded && <>
        <ManuscriptCover recordId={record.id} available={record.has_manuscript ?? record.file_count > 0} />
        <div className="mt-auto border-t border-stone-200 px-5 pb-5 pt-4">
          <div className="flex items-center gap-2">
            <span aria-hidden className="h-0.5 w-4 rounded-full bg-brand" />
            <span className="text-label font-semibold uppercase tracking-wide text-stone-700">{record.ai_hook?.trim() ? "At a glance" : "From the abstract"}</span>
          </div>
          <p className="mt-2 line-clamp-3 font-display text-[1.13rem] leading-snug text-stone-800">
            {hook ? highlightMatch(hook, searchHighlight) : "No abstract has been added yet."}
          </p>
        </div>
      </>}
      footerClassName="rounded-b-xl border-stone-200 bg-white"
      footer={
        <>
          <ResearchOriginBadge origin={record.origin} />
          <span className="inline-flex items-center gap-1.5 text-stone-700" title="Times this record has been opened">
            <i className="fas fa-eye text-[12px] text-brand" aria-hidden />
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
              "w-11 h-11 [@media(pointer:fine)]:w-9 [@media(pointer:fine)]:h-9 rounded-lg border bg-white flex items-center justify-center",
              COLOUR_TRANSITION,
              FOCUS_RING,
              starred
                ? "border-stone-300 bg-stone-100 text-brand"
                : "border-stone-200 text-stone-600 hover:text-brand hover:border-stone-400 hover:bg-stone-50",
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
              "w-11 h-11 [@media(pointer:fine)]:w-9 [@media(pointer:fine)]:h-9 rounded-lg border border-stone-200 bg-white text-stone-600 hover:text-brand hover:border-stone-400 hover:bg-stone-50 flex items-center justify-center",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <CitationIcon className="w-[13px] h-[13px]" />
          </button>
          {onNotInterested && (
            <button
              type="button"
              onClick={onNotInterested}
              aria-label="Not interested"
              title="Not interested"
              className={cn(
                "w-11 h-11 [@media(pointer:fine)]:w-9 [@media(pointer:fine)]:h-9 rounded-lg border border-stone-200 bg-white text-stone-600 hover:text-brand hover:border-stone-400 hover:bg-stone-50 flex items-center justify-center",
                COLOUR_TRANSITION,
                FOCUS_RING,
              )}
            >
              <i className="far fa-eye-slash text-[13px]" aria-hidden />
            </button>
          )}
        </>
      }
    />
  );
}
