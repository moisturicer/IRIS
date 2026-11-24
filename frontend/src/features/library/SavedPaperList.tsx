import { Link, useNavigate } from "react-router-dom";
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

/** Three looks that cannot be mistaken for each other: an outline, an ink fill, a green outline. Each carries its icon and word. */
const STATUS_LABEL_TONE: Record<string, string> = {
  want_to_read: "bg-transparent text-stone-700 ring-1 ring-stone-300",
  reading:      "bg-stone-900 text-white",
  completed:    "bg-surface text-cleared ring-1 ring-cleared-line",
};

const STATUS_MENU_ICON: Record<string, string> = { want_to_read: "fa-clock", reading: "fa-book-open", completed: "fa-circle-check" };

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
  const navigate = useNavigate();
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
        // Open, Reading status as a flyout, then Cite and Remove behind one hairline.
        const menu: RowMenuItem[] = [
          { key: "open", label: "Open paper", icon: "fa-arrow-up-right-from-square", onSelect: () => navigate(`/records/${record.id}`) },
          ...(saved
            ? [{
                key: "status",
                label: "Reading status",
                icon: "fa-book-open",
                onSelect: () => undefined,
                submenu: READING_STATUSES.map((option) => ({
                  key: option.value,
                  label: option.label,
                  icon: STATUS_MENU_ICON[option.value] ?? option.icon,
                  checked: status === option.value,
                  onSelect: () => onSetStatus(record, status === option.value ? null : option.value),
                })),
              }]
            : []),
          ...(citable ? [{ key: "cite", label: "Cite", icon: "fa-quote-right", separatorBefore: true, onSelect: () => onCite(record) }] : []),
          ...(onRemove
            ? [{ key: "remove", label: removeLabel, icon: "fa-bookmark", separatorBefore: !citable, onSelect: () => onRemove(record.id) }]
            : []),
        ];

        return (
          <li
            key={record.id}
            className={cn(
              "group relative flex items-center gap-3 px-4 py-3 sm:px-5",
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
                className={cn("relative z-10 h-4 w-4 shrink-0 accent-brand", FOCUS_RING)}
              />
            )}
            {/* The Reading status stands at the row's end, or under the paper on a phone. */}
            <div className="flex min-w-0 flex-1 flex-col items-start gap-x-6 gap-y-2 md:flex-row md:items-center">
            <div className="min-w-0 md:flex-1">
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
              <p className="mt-0.5 flex flex-wrap gap-x-2 break-words text-small text-stone-600">
                <span className={authors === "Authors not recorded" ? "italic" : undefined}>{authors}</span>
                {year && year !== "—" && <span><span aria-hidden>· </span>{year}</span>}
                {record.record_type_name && <span><span aria-hidden>· </span>{record.record_type_name}</span>}
              </p>
              {(viewed || badges.length > 0) && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  {badges.map((badge) => (
                    <span key={badge.label} className={cn("rounded-control px-1.5 py-0.5 text-label font-semibold", BADGE_TONE_CLASS[badge.tone])}>
                      {badge.label}
                    </span>
                  ))}
                  {viewed && <span className="text-label text-stone-500">{viewed}</span>}
                </div>
              )}
            </div>
              {status && (
                <span className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-label font-semibold", STATUS_LABEL_TONE[status])}>
                  <i className={cn("fas text-2xs", STATUS_MENU_ICON[status])} aria-hidden />
                  {readingStatusLabel(status)}
                </span>
              )}
            </div>
            <div className="relative z-10 -mr-2 shrink-0">
              <RowMenu small vertical label={`Actions for ${record.title}`} items={menu} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
