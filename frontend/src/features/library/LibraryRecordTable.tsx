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

export type LibraryLayout = "list" | "grid";

interface LibraryRecordTableProps {
  records: RecordListItem[];
  layout: LibraryLayout;
  query: string;
  selected: Set<number>;
  onToggleSelect: (id: number) => void;
  onToggleAll: () => void;
  starred: Set<number>;
  onToggleStar: (id: number) => void;
  onCite: (record: RecordListItem) => void;
  onRemove: (id: number) => void;
  /** ISO timestamps, only supplied by the reading-history view. */
  viewedAt?: Record<number, string>;
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
  starred,
  onToggleStar,
  onCite,
  onRemove,
  viewedAt,
}: LibraryRecordTableProps) {
  const allSelected = records.length > 0 && records.every((r) => selected.has(r.id));

  const star = (record: RecordListItem) => {
    const isOn = starred.has(record.id);
    return (
      <button
        type="button"
        onClick={() => onToggleStar(record.id)}
        aria-label={isOn ? `Unlike ${record.title}` : `Like ${record.title}`}
        aria-pressed={isOn}
        title={isOn ? "Liked" : "Like"}
        className="p-0.5 shrink-0"
      >
        <i
          className={cn(
            "fa-star text-[13px] transition-colors",
            isOn ? "fas text-gold" : "far text-stone-300 hover:text-gold",
          )}
        />
      </button>
    );
  };

  const actions = (record: RecordListItem) => (
    <div className="flex items-center gap-0.5">
      <button
        type="button"
        onClick={() => onCite(record)}
        aria-label={`Cite ${record.title}`}
        title="Cite"
        className="p-1.5 rounded-md text-stone-400 hover:text-brand hover:bg-stone-100 transition-colors"
      >
        <i className="fas fa-quote-right text-[11px]" />
      </button>
      <button
        type="button"
        onClick={() => onRemove(record.id)}
        aria-label={`Remove ${record.title} from library`}
        title="Remove from library"
        className="p-1.5 rounded-md text-stone-400 hover:text-brand hover:bg-stone-100 transition-colors"
      >
        <i className="fas fa-bookmark text-[11px]" />
      </button>
    </div>
  );

  const badges = (record: RecordListItem) => {
    const list = statusBadges(record);
    if (list.length === 0) {
      return <span className="text-[12px] text-stone-300">—</span>;
    }
    return (
      <div className="flex flex-wrap gap-1">
        {list.map((badge) => (
          <span
            key={badge.label}
            className={cn(
              "px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap",
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
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {records.map((record) => (
          <div
            key={record.id}
            className={cn(
              "relative bg-white border rounded-xl p-4 transition-colors",
              selected.has(record.id) ? "border-brand/40" : "border-stone-200 hover:border-stone-300",
            )}
          >
            <div className="flex items-start gap-2 mb-2">
              <input
                type="checkbox"
                checked={selected.has(record.id)}
                onChange={() => onToggleSelect(record.id)}
                aria-label={`Select ${record.title}`}
                className="mt-1 accent-brand"
              />
              {star(record)}
              <Link
                to={`/records/${record.id}`}
                className="flex-1 min-w-0 text-[13px] font-semibold text-stone-900 hover:text-brand leading-snug line-clamp-2"
              >
                {highlightMatch(record.title, query)}
              </Link>
            </div>
            <p className="text-[12px] text-stone-500 truncate mb-1">
              {formatAuthorList(record.authors, 2)}
            </p>
            <p className="text-[11px] text-stone-400 mb-2.5">
              {recordYearLabel(record)}
              {viewedLabel(viewedAt?.[record.id]) && ` · ${viewedLabel(viewedAt?.[record.id])}`}
            </p>
            <div className="flex items-end justify-between gap-2">
              {badges(record)}
              {actions(record)}
            </div>
          </div>
        ))}
      </div>
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
        <span className="text-[10px] font-bold uppercase tracking-wider text-stone-400">Title</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-stone-400">Authors</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-stone-400">Published</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-stone-400">Status / IP</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-stone-400 text-right">
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
              selected.has(record.id) ? "bg-brand-50/40" : "hover:bg-stone-50",
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
              <span className="md:hidden">{star(record)}</span>
            </div>

            <div className="min-w-0 flex items-center gap-2">
              <span className="hidden md:block">{star(record)}</span>
              <div className="min-w-0">
                <Link
                  to={`/records/${record.id}`}
                  // Two lines rather than one: recognising the paper is the whole
                  // point of the row, and a mid-phrase ellipsis defeats it.
                  className="block text-[13px] font-semibold text-stone-900 hover:text-brand leading-snug line-clamp-2"
                >
                  {highlightMatch(record.title, query)}
                </Link>
                {viewedLabel(viewedAt?.[record.id]) && (
                  <p className="text-[11px] text-stone-400 mt-0.5">
                    {viewedLabel(viewedAt?.[record.id])}
                  </p>
                )}
              </div>
            </div>

            <p className="text-[12px] text-stone-500 truncate">
              <span className="md:hidden text-stone-400">By </span>
              {formatAuthorList(record.authors, 2)}
            </p>

            <p className="text-[12px] text-stone-500 tabular-nums">{recordYearLabel(record)}</p>

            {badges(record)}

            <div className="md:justify-self-end">{actions(record)}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
