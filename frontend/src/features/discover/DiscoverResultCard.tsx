import { ResearchCard } from "@/components/shared/ResearchCard";
import { ResearchOriginBadge } from "@/components/shared/ResearchOriginBadge";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type { ForYouItem, RecordListItem } from "@/types/records";
import { CitationIcon } from "./DiscoverIcons";
import { PaperThumbnail } from "./PaperThumbnail";
import { PaperSaveDropdown } from "./PaperSaveDropdown";
import {
  formatAuthorList,
  ipTypeLabel,
  indexedOnLabel,
  recordYearLabel,
} from "./discoverUtils";
import { highlightTerms } from "./searchTerms";

interface DiscoverResultCardProps {
  record:          RecordListItem;
  searchHighlight: string;
  onCite:          () => void;
  reason?:         ForYouItem["reason"];
  /** One column: a list row with a 96 px outline thumbnail. Two and three columns are text-only tiles. */
  row?:            boolean;
  /** For you only: hide this recommendation for the reader's account (IR-576). */
  onNotInterested?: () => void;
}

/** What a For you reason says. A chosen Area is named; a saved one deliberately is not. */
function reasonLabel(reason: ForYouItem["reason"]): string {
  if (reason.kind === "selected_area" && reason.area) return `Because you chose ${reason.area}`;
  if (reason.kind === "saved_area") return "Same Area as a paper you saved";
  return "Latest research";
}

/**
 * A Discover result: `ResearchCard` filled from the list payload (IR-407,
 * spec §4.3 and §4.12).
 *
 * It shows only what `RecordListItem` carries. The list payload has no college,
 * so the card names none rather than guessing one; citation and download
 * counts do not exist, so views are the only figure.
 */
export function DiscoverResultCard({ record, searchHighlight, onCite, reason, row = false, onNotInterested }: DiscoverResultCardProps) {
  const abstract = record.abstract?.trim() ?? "";

  const flags = [
    record.is_ip && { key: "ip", icon: "fa-shield-halved", label: ipTypeLabel(record.ip_type) },
    record.for_commercialization && { key: "commercial", icon: "fa-store", label: "Commercialization" },
    record.community_extension && { key: "extension", icon: "fa-people-group", label: "Community extension" },
  ].filter(Boolean) as { key: string; icon: string; label: string }[];

  return (
    <ResearchCard
      layout={row ? "list" : "grid"}
      compact={row}
      href={`/records/${record.id}`}
      title={record.title}
      titleContent={highlightTerms(record.title, searchHighlight)}
      eyebrow={
        <span className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          {record.classification_name && <span className="text-brand">{record.classification_name}</span>}
          {record.classification_name && record.record_type_name && (
            <span aria-hidden="true" className="text-stone-400">·</span>
          )}
          {record.record_type_name && <span>{record.record_type_name}</span>}
          {reason && <span aria-label="Why this was suggested" className="inline-flex rounded-md bg-stone-100 px-1.5 py-0.5 text-[11px] font-medium text-stone-700">
            {reasonLabel(reason)}
          </span>}
        </span>
      }
      meta={record.publication_year ? `Published ${recordYearLabel(record)}` : indexedOnLabel(record)}
      byline={formatAuthorList(record.authors) === "Authors not recorded"
        ? <span className="italic text-stone-500">Authors not recorded</span>
        : highlightTerms(formatAuthorList(record.authors), searchHighlight)}
      summary={abstract ? highlightTerms(abstract, searchHighlight) : <span className="italic">No abstract provided.</span>}
      summaryClassName={row ? "line-clamp-2" : undefined}
      thumbnail={row && <PaperThumbnail />}
      footerClassName={row ? undefined : "rounded-b-xl border-stone-200 bg-white"}
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
