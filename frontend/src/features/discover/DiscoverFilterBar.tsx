import { useState } from "react";

import { Modal } from "@/components/ui/Modal";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import { ALL_VALUE, DiscoverFilterDropdown, type FilterOption } from "./DiscoverFilterDropdown";

/**
 * What Discover is narrowed by (spec §4.3). Each field maps to a query param
 * the list endpoint already understands; `DiscoverPage` does that mapping.
 *
 * `ip` is one control for two params: "has IP" is `is_ip=true`, and a single
 * IP type is `ip_type=<code>` (which implies IP).
 */
export interface DiscoverFilters {
  recordType:      string;
  colleges:        string[];
  classifications: string[];
  year:            string;
  ip:              string;
}

export const EMPTY_FILTERS: DiscoverFilters = {
  recordType: ALL_VALUE,
  colleges: [],
  classifications: [],
  year: ALL_VALUE,
  ip: ALL_VALUE,
};

/** The IP control's "has any IP" value, as opposed to one IP type. */
export const HAS_IP = "has_ip";

export type DiscoverSort = "newest" | "viewed";

export const SORT_OPTIONS: FilterOption[] = [
  { value: "newest", label: "Newest" },
  { value: "viewed", label: "Most viewed" },
];

export interface DiscoverFilterOptions {
  recordTypes:     FilterOption[];
  colleges:        FilterOption[];
  classifications: FilterOption[];
  years:           FilterOption[];
  ip:              FilterOption[];
}

interface DiscoverFilterBarProps {
  filters:   DiscoverFilters;
  onChange:  (next: DiscoverFilters) => void;
  sort:      DiscoverSort;
  onSort:    (next: DiscoverSort) => void;
  options:   DiscoverFilterOptions;
  /** Reference data still loading: the lists say so rather than look empty. */
  loading:   boolean;
  /** How many results the current filters return, for the sheet's button. */
  resultCount: number | null;
}

interface Chip {
  key:    string;
  label:  string;
  remove: () => void;
}

export function activeFilterCount(filters: DiscoverFilters): number {
  return (
    filters.colleges.length +
    filters.classifications.length +
    (filters.recordType !== ALL_VALUE ? 1 : 0) +
    (filters.year !== ALL_VALUE ? 1 : 0) +
    (filters.ip !== ALL_VALUE ? 1 : 0)
  );
}

/**
 * The filter bar: a row of filters and a Sort menu, the active filters as
 * removable chips, and below `md` a "Filters" button that opens the same
 * filters in a sheet (spec §4.3, §4.13).
 */
export function DiscoverFilterBar({
  filters,
  onChange,
  sort,
  onSort,
  options,
  loading,
  resultCount,
}: DiscoverFilterBarProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const count = activeFilterCount(filters);

  const set = <K extends keyof DiscoverFilters>(key: K, value: DiscoverFilters[K]) =>
    onChange({ ...filters, [key]: value });

  const labelOf = (list: FilterOption[], value: string) =>
    list.find((o) => o.value === value)?.label ?? value;

  const chips: Chip[] = [
    ...(filters.recordType !== ALL_VALUE
      ? [{ key: "type", label: labelOf(options.recordTypes, filters.recordType), remove: () => set("recordType", ALL_VALUE) }]
      : []),
    ...filters.colleges.map((id) => ({
      key: `college-${id}`,
      label: labelOf(options.colleges, id),
      remove: () => set("colleges", filters.colleges.filter((c) => c !== id)),
    })),
    ...filters.classifications.map((id) => ({
      key: `classification-${id}`,
      label: labelOf(options.classifications, id),
      remove: () => set("classifications", filters.classifications.filter((c) => c !== id)),
    })),
    ...(filters.year !== ALL_VALUE
      ? [{ key: "year", label: filters.year, remove: () => set("year", ALL_VALUE) }]
      : []),
    ...(filters.ip !== ALL_VALUE
      ? [{ key: "ip", label: labelOf(options.ip, filters.ip), remove: () => set("ip", ALL_VALUE) }]
      : []),
  ];

  /** The five filters, laid out by the caller: a row, or the sheet's stack. */
  const controls = (stacked: boolean) => {
    const shared = { inline: stacked, block: stacked };
    return (
      <>
        <DiscoverFilterDropdown
          {...shared}
          name="Type"
          options={options.recordTypes}
          selected={filters.recordType}
          onChange={(v) => set("recordType", v)}
          loading={loading}
        />
        <DiscoverFilterDropdown
          {...shared}
          multi
          name="College"
          options={options.colleges}
          selected={filters.colleges}
          onChange={(v) => set("colleges", v)}
          loading={loading}
          emptyHint="No colleges found."
        />
        <DiscoverFilterDropdown
          {...shared}
          multi
          name="Classification"
          options={options.classifications}
          selected={filters.classifications}
          onChange={(v) => set("classifications", v)}
          loading={loading}
          emptyHint="No classifications recorded yet."
        />
        <DiscoverFilterDropdown
          {...shared}
          name="Year"
          options={options.years}
          selected={filters.year}
          onChange={(v) => set("year", v)}
        />
        <DiscoverFilterDropdown
          {...shared}
          name="IP & patents"
          options={options.ip}
          selected={filters.ip}
          onChange={(v) => set("ip", v)}
        />
      </>
    );
  };

  return (
    <div className="mt-6">
      <div className="flex items-center gap-2">
        {/* At md and up the filters are one row. */}
        <div role="group" aria-label="Filter research" className="hidden md:flex flex-wrap items-center gap-2">
          {controls(false)}
        </div>

        {/* Below md they live in a sheet, so results are not pushed off-screen. */}
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          aria-haspopup="dialog"
          className={cn(
            "md:hidden inline-flex items-center gap-2 min-h-[40px] px-4 rounded-full border text-small font-medium",
            COLOUR_TRANSITION,
            FOCUS_RING,
            count > 0 ? "bg-brand-50 border-brand text-brand" : "bg-white border-stone-300 text-stone-700",
          )}
        >
          <i className="fas fa-sliders text-[12px]" aria-hidden />
          <span>Filters</span>
          {count > 0 && (
            <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-brand text-white text-label font-semibold flex items-center justify-center">
              {count}
              <span className="sr-only"> active</span>
            </span>
          )}
        </button>

        <div className="ml-auto shrink-0">
          <DiscoverFilterDropdown
            neutral
            name="Sort"
            options={SORT_OPTIONS}
            selected={sort}
            onChange={(v) => onSort(v as DiscoverSort)}
          />
        </div>
      </div>

      {chips.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <ul aria-label="Active filters" className="flex flex-wrap items-center gap-2">
            {chips.map((chip) => (
              <li key={chip.key}>
                <button
                  type="button"
                  onClick={chip.remove}
                  aria-label={`Remove filter: ${chip.label}`}
                  className={cn(
                    "inline-flex items-center gap-1.5 min-h-[32px] pl-3 pr-2.5 rounded-full bg-stone-100 text-small text-stone-800 hover:bg-stone-200",
                    COLOUR_TRANSITION,
                    FOCUS_RING,
                  )}
                >
                  <span>{chip.label}</span>
                  <i className="fas fa-xmark text-[12px] text-stone-600" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
            className={cn(
              "min-h-[32px] px-2 rounded-md text-small font-medium text-brand hover:underline underline-offset-2",
              FOCUS_RING,
            )}
          >
            Clear all filters
          </button>
        </div>
      )}

      <Modal
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        title="Filters"
        sheet
        footer={
          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => onChange(EMPTY_FILTERS)}
              disabled={count === 0}
              className={cn(PILL_SECONDARY, "disabled:opacity-50 disabled:pointer-events-none")}
            >
              Clear all
            </button>
            <button type="button" onClick={() => setSheetOpen(false)} className={PILL_PRIMARY}>
              {resultCount === null ? "Show results" : `Show ${resultCount} result${resultCount === 1 ? "" : "s"}`}
            </button>
          </div>
        }
      >
        <div className="flex flex-col gap-3">{controls(true)}</div>
      </Modal>
    </div>
  );
}
