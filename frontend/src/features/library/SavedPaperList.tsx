import { Link } from "react-router-dom";
import { formatDistanceToNow, isValid, parseISO } from "date-fns";

import type { ReadingStatus } from "@/api/library";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { RowMenu, type RowMenuItem } from "@/features/accounts/RowMenu";
import {
  BADGE_TONE_CLASS,
  formatAuthorList,
  highlightMatch,
  metaBadges,
  recordYearLabel,
} from "@/features/discover/discoverUtils";
import { PIPELINE_STATUS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { READING_STATUSES, readingStatusLabel } from "@/store/library.store";
import type { RecordListItem } from "@/types/records";

interface SavedPaperListProps {
  records: RecordListItem[];
  query: string;
  /** Choosing papers to remove together: each row shows its checkbox. */
  selecting: boolean;
  selected: Set<number>;
  onToggleSelect: (id: number) => void;
  onCite: (record: RecordListItem) => void;
  /** Omitted where a paper cannot be taken out of the view (history). */
  onRemove?: (id: number) => void;
  /** What removing does here: "Remove from library" or "Remove from folder". */
  removeLabel?: string;
  /** ISO timestamps, only supplied by the reading-history view. */
  viewedAt?: Record<number, string>;
  /** The account's Reading status per saved paper (IR-566); absent for a paper that is not saved. */
  readingStatusOf: Record<number, ReadingStatus | null>;
  /** Set or clear a saved paper's Reading status; the checked one clears it, as the Save menu does. */
  onSetStatus: (record: RecordListItem, status: ReadingStatus | null) => void;
}

/** Only the provenance badges: the title row already says the topic and type. */
const provenance = (record: RecordListItem) =>
  metaBadges(record).filter((b) => b.tone === "ip" || b.tone === "commercial" || b.tone === "extension");

function viewedLabel(iso: string | undefined): string | null {
  if (!iso) return null;
  const parsed = parseISO(iso);
  return isValid(parsed) ? `Viewed ${formatDistanceToNow(parsed, { addSuffix: true })}` : null;
}

/**
 * Saved papers as one ruled list (IR-1311, replacing the table and the card
 * grid). The title is the row's link, stretched over the row. Every act on a
 * paper is in its ⋯ menu: its Reading status, Cite (a published paper only,
 * mirroring the server's `cite` rule, IR-1305) and removing it from this view.
 */
export function SavedPaperList({
  records, query, selecting, selected, onToggleSelect, onCite, onRemove,
  removeLabel = "Remove from library", viewedAt, readingStatusOf, onSetStatus,
}: SavedPaperListProps) {
  return (
    <ul className="divide-y divide-stone-100 overflow-hidden rounded-card border border-stone-200 bg-white">
      {records.map((record) => {
        const saved = record.id in readingStatusOf;
        const status = readingStatusOf[record.id] ?? null;
        const viewed = viewedLabel(viewedAt?.[record.id]);
        const authors = formatAuthorList(record.authors, 2);
        const year = recordYearLabel(record);
        const badges = provenance(record);

        const citable = record.pipeline_status === PIPELINE_STATUS.PUBLISHED;
        // Reading status, then Cite and Remove behind one hairline.
        const menu: RowMenuItem[] = [
          ...(saved
            ? READING_STATUSES.map((option) => ({
                key: option.value,
                label: option.label,
                checked: status === option.value,
                onSelect: () => onSetStatus(record, status === option.value ? null : option.value),
              }))
            : []),
          ...(citable ? [{ key: "cite", label: "Cite", separatorBefore: saved, onSelect: () => onCite(record) }] : []),
          ...(onRemove
            ? [{ key: "remove", label: removeLabel, separatorBefore: saved && !citable, onSelect: () => onRemove(record.id) }]
            : []),
        ];

        return (
          <li
            key={record.id}
            className={cn(
              "group relative flex items-start gap-3 px-4 py-4 sm:px-5",
              COLOUR_TRANSITION,
              selected.has(record.id) ? "bg-stone-100" : "hover:bg-stone-50",
            )}
          >
            {selecting && (
              <input
                type="checkbox"
                checked={selected.has(record.id)}
                onChange={() => onToggleSelect(record.id)}
                aria-label={`Select ${record.title}`}
                className={cn("relative z-10 mt-1.5 h-4 w-4 shrink-0 accent-brand", FOCUS_RING)}
              />
            )}
            <div className="min-w-0 flex-1">
              <h3 className="font-display text-title font-semibold leading-snug text-stone-900">
                <Link
                  to={`/records/${record.id}`}
                  className={cn(
                    "break-words rounded-control group-hover:text-brand",
                    COLOUR_TRANSITION,
                    FOCUS_RING,
                    "after:absolute after:inset-0 after:content-['']",
                  )}
                >
                  {highlightMatch(record.title, query)}
                </Link>
              </h3>
              <p className="mt-1 flex flex-wrap gap-x-2 break-words text-small text-stone-600">
                <span className={authors === "Authors not recorded" ? "italic" : undefined}>{authors}</span>
                {year && year !== "—" && <span><span aria-hidden>· </span>{year}</span>}
                {record.record_type_name && <span><span aria-hidden>· </span>{record.record_type_name}</span>}
              </p>
              {(status || viewed || badges.length > 0) && (
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {status && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-0.5 text-label font-semibold text-stone-700 ring-1 ring-stone-300">
                      <i className={cn("fas text-2xs", READING_STATUSES.find((s) => s.value === status)?.icon)} aria-hidden />
                      {readingStatusLabel(status)}
                    </span>
                  )}
                  {badges.map((badge) => (
                    <span key={badge.label} className={cn("rounded-control px-1.5 py-0.5 text-label font-semibold", BADGE_TONE_CLASS[badge.tone])}>
                      {badge.label}
                    </span>
                  ))}
                  {viewed && <span className="text-label text-stone-500">{viewed}</span>}
                </div>
              )}
            </div>
            {menu.length > 0 && (
              <div className="relative z-10 -mr-2 -mt-1 shrink-0">
                <RowMenu small label={`Actions for ${record.title}`} items={menu} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
