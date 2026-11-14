import { Link } from "react-router-dom";
import { formatDistanceToNow, parseISO, isValid } from "date-fns";
import type { RecordListItem } from "@/types/records";
import {
  BADGE_TONE_CLASS,
  formatAuthorList,
  highlightMatch,
  metaBadges,
  recordYearLabel,
} from "@/features/discover/discoverUtils";
import { cn } from "@/lib/utils";
import type { ReadingStatus } from "@/api/library";
import { READING_STATUSES, readingStatusLabel } from "@/store/library.store";

export type LibraryLayout = "list" | "grid";

interface LibraryRecordTableProps {
  records: RecordListItem[];
  layout: LibraryLayout;
  query: string;
  selected: Set<number>;
  onToggleSelect: (id: number) => void;
  onToggleAll: () => void;
  onCite: (record: RecordListItem) => void;
  /** Omitted where a paper cannot be taken out of the view (history). */
  onRemove?: (id: number) => void;
  /** What removing does here: "Remove from library" or "Remove from folder". */
  removeLabel?: string;
  /** ISO timestamps, only supplied by the reading-history view. */
  viewedAt?: Record<number, string>;
  /** The account's Reading status per saved paper (IR-566), shown on a grid card. */
  readingStatusOf?: Record<number, ReadingStatus | null>;
}

/**
 * Only the three provenance badges belong in a STATUS / IP column — the topic
 * and record-type badges are already carried by the title row on Discover, and
 * repeating them here would crowd out the one thing this column is for.
 */
function statusBadges(record: RecordListItem) {
  return metaBadges(record).filter(
    (b) => b.tone === "ip" || b.tone === "commercial" || b.tone === "extension",
  );
}

function viewedLabel(iso: string | undefined): string | null {
  if (!iso) return null;
  const parsed = parseISO(iso);
  if (!isValid(parsed)) return null;
  return `Viewed ${formatDistanceToNow(parsed, { addSuffix: true })}`;
}

const ROW_GRID = "md:grid-cols-[1.5rem_minmax(0,1fr)_11rem_5rem_10rem_4.5rem]";

export function LibraryRecordTable({
  records,
  layout,
  query,
  selected,
  onToggleSelect,
  onToggleAll,
  onCite,
  onRemove,
  removeLabel = "Remove from library",
  viewedAt,
  readingStatusOf,
}: LibraryRecordTableProps) {
  const allSelected = records.length > 0 && records.every((r) => selected.has(r.id));

  const actions = (record: RecordListItem) => (
    <div className="flex items-center gap-0.5">
      <button
        type="button"
        onClick={() => onCite(record)}
        aria-label={`Cite ${record.title}`}
        title="Cite"
        className="p-1.5 rounded-md text-stone-400 hover:text-brand hover:bg-stone-100 transition-colors"
      >
        <i className="fas fa-quote-right text-[12px]" aria-hidden />
      </button>
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(record.id)}
          aria-label={`${removeLabel}: ${record.title}`}
          title={removeLabel}
          className="p-1.5 rounded-md text-stone-400 hover:text-brand hover:bg-stone-100 transition-colors"
        >
          <i className="fas fa-bookmark text-[12px]" aria-hidden />
        </button>
      )}
    </div>
  );

  const badges = (record: RecordListItem, dash = true) => {
    const list = statusBadges(record);
    if (list.length === 0) {
      return dash ? <span className="text-[13px] text-stone-300">—</span> : null;
    }
    return (
      <div className="flex flex-wrap gap-1">
        {list.map((badge) => (
          <span
            key={badge.label}
            className={cn(
              "px-1.5 py-0.5 rounded text-[11px] font-semibold whitespace-nowrap",
              BADGE_TONE_CLASS[badge.tone],
            )}
          >
            {badge.label}
          </span>
        ))}
      </div>
    );
  };

  if (layout === "grid") {
    return (
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {records.map((record) => {
          const status = readingStatusOf?.[record.id];
          const viewed = viewedLabel(viewedAt?.[record.id]);
          return (
            <li
              key={record.id}
              className={cn(
                "group relative flex flex-col rounded-2xl border bg-white p-card-compact transition-[border-color,box-shadow] duration-200 hover:shadow-card-md md:p-card",
                selected.has(record.id) ? "border-stone-900" : "border-stone-200",
              )}
            >
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.has(record.id)}
                  onChange={() => onToggleSelect(record.id)}
                  aria-label={`Select ${record.title}`}
                  className="relative z-10 h-4 w-4 accent-brand"
                />
                <p className="min-w-0 flex-1 truncate text-label text-stone-600">
                  {[record.record_type_name, recordYearLabel(record)].filter((part) => part && part !== "—").join(" · ")}
                </p>
                <div className="relative z-10 -mr-1.5">{actions(record)}</div>
              </div>
              <h3 className="mt-2 font-display text-title font-semibold leading-snug text-stone-900">
                <Link
                  to={`/records/${record.id}`}
                  className="line-clamp-3 rounded-sm transition-colors group-hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 after:absolute after:inset-0 after:rounded-2xl after:content-['']"
                >
                  {highlightMatch(record.title, query)}
                </Link>
              </h3>
              <p className="mt-1 truncate text-small text-stone-600">
                <span className={formatAuthorList(record.authors, 2) === "Authors not recorded" ? "italic" : undefined}>{formatAuthorList(record.authors, 2)}</span>
              </p>
              {viewed && <p className="mt-0.5 text-label text-stone-500">{viewed}</p>}
              <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4">
                {status && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-0.5 text-2xs font-semibold text-brand ring-1 ring-stone-300">
                    <i className={cn("fas", READING_STATUSES.find((s) => s.value === status)?.icon)} aria-hidden />
                    {readingStatusLabel(status)}
                  </span>
                )}
                {badges(record, false)}
              </div>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div className="bg-white border border-stone-200 rounded-2xl overflow-hidden">
      {/* Column headings only make sense once the row is actually columnar. */}
      <div
        className={cn(
          "hidden md:grid gap-3 items-center px-4 py-2.5 bg-stone-50 border-b border-stone-200",
          ROW_GRID,
        )}
      >
        <input
          type="checkbox"
          checked={allSelected}
          onChange={onToggleAll}
          aria-label="Select all records"
          className="accent-brand"
        />
        <span className="text-[11px] font-bold uppercase tracking-wider text-stone-400">Title</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-stone-400">Authors</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-stone-400">Published</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-stone-400">Status / IP</span>
        <span className="text-[11px] font-bold uppercase tracking-wider text-stone-400 text-right">
          Actions
        </span>
      </div>

      <ul className="divide-y divide-stone-100">
        {records.map((record) => (
          <li
            key={record.id}
            className={cn(
              "grid gap-x-3 gap-y-1.5 items-start md:items-center px-4 py-3 transition-colors",
              ROW_GRID,
              selected.has(record.id) ? "bg-stone-100" : "hover:bg-stone-50",
            )}
          >
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selected.has(record.id)}
                onChange={() => onToggleSelect(record.id)}
                aria-label={`Select ${record.title}`}
                className="accent-brand"
              />
            </div>

            <div className="min-w-0 flex items-center gap-2">
              <div className="min-w-0">
                <Link
                  to={`/records/${record.id}`}
                  // Two lines rather than one: recognising the paper is the whole
                  // point of the row, and a mid-phrase ellipsis defeats it.
                  className="block text-[14px] font-semibold text-stone-900 hover:text-brand leading-snug line-clamp-2"
                >
                  {highlightMatch(record.title, query)}
                </Link>
                {viewedLabel(viewedAt?.[record.id]) && (
                  <p className="text-[12px] text-stone-400 mt-0.5">
                    {viewedLabel(viewedAt?.[record.id])}
                  </p>
                )}
              </div>
            </div>

            <p className="text-[13px] text-stone-500 truncate">
              <span className="md:hidden text-stone-400">By </span>
              <span className={formatAuthorList(record.authors, 2) === "Authors not recorded" ? "italic text-stone-500" : undefined}>{formatAuthorList(record.authors, 2)}</span>
            </p>

            <p className="text-[13px] text-stone-500 tabular-nums">{recordYearLabel(record)}</p>

            {badges(record)}

            <div className="md:justify-self-end">{actions(record)}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
