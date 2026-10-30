import { useEffect, useId, useRef, useState } from "react";

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
  className?: string;
  filters:   DiscoverFilters;
  onChange:  (next: DiscoverFilters) => void;
  showSort?: boolean;
  sort:      DiscoverSort;
  onSort:    (next: DiscoverSort) => void;
  options:   DiscoverFilterOptions;
  /** Reference data still loading: the lists say so rather than look empty. */
  loading:   boolean;
  /** How many results the current filters return, for the sheet's button. */
  resultCount: number | null;
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
 * One Filters control keeps the feed toolbar compact at every width. Its
 * dropdown holds every catalogue filter and the optional Latest sort control.
 */
export function DiscoverFilterBar({
  className,
  filters,
  onChange,
  showSort = true,
  sort,
  onSort,
  options,
  loading,
  resultCount,
}: DiscoverFilterBarProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const count = activeFilterCount(filters);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  const set = <K extends keyof DiscoverFilters>(key: K, value: DiscoverFilters[K]) =>
    onChange({ ...filters, [key]: value });

  const controls = () => {
    const shared = { inline: true, block: true };
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
          name="Year (completed)"
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
    <div ref={rootRef} className={cn("relative flex min-w-0 items-center justify-end", className)}>
        <button
          type="button"
          ref={triggerRef}
          onClick={() => setOpen((value) => !value)}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          aria-label={count ? `Filters, ${count} active` : "Filters"}
          className={cn(
            "relative inline-flex h-11 w-11 sm:w-auto sm:px-3 items-center justify-center gap-2 rounded-lg border text-small font-medium",
            COLOUR_TRANSITION,
            FOCUS_RING,
            count > 0 ? "bg-brand-50 border-brand text-brand" : "bg-white border-stone-300 text-stone-700",
          )}
        >
          <i className="fas fa-sliders text-[12px]" aria-hidden />
          <span className="hidden sm:inline">Filters</span>
          {count > 0 && (
            <span className="absolute -right-1 -top-1 sm:static min-w-[18px] h-[18px] px-1 rounded-full bg-brand text-white text-label font-semibold flex items-center justify-center">
              {count}
              <span className="sr-only"> active</span>
            </span>
          )}
        </button>

      {open && <div id={panelId} role="dialog" aria-label="Filters"
        className="fixed inset-x-4 bottom-4 z-50 flex max-h-[min(80dvh,34rem)] flex-col rounded-xl border border-stone-200 bg-white shadow-card-md sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[22rem]">
        <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3">
          <h2 className="text-small font-semibold text-stone-900">Filters</h2>
          <button type="button" ref={closeRef} onClick={() => { setOpen(false); triggerRef.current?.focus(); }} aria-label="Close filters"
            className={cn("flex h-9 w-9 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100", FOCUS_RING)}>
            <i className="fas fa-xmark text-[13px]" aria-hidden />
          </button>
        </div>
        <div className="flex flex-col gap-3 overflow-y-auto px-4 py-4">
          {controls()}
          {showSort && <DiscoverFilterDropdown
            inline block neutral name="Sort" options={SORT_OPTIONS} selected={sort}
            onChange={(v) => onSort(v as DiscoverSort)}
          />}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-stone-100 px-4 py-3">
            <button
              type="button"
              onClick={() => onChange(EMPTY_FILTERS)}
              disabled={count === 0}
              className={cn(PILL_SECONDARY, "disabled:opacity-50 disabled:pointer-events-none")}
            >
              Clear all
            </button>
            <button type="button" onClick={() => { setOpen(false); triggerRef.current?.focus(); }} className={PILL_PRIMARY}>
              {resultCount === null ? "Show results" : `Show ${resultCount} result${resultCount === 1 ? "" : "s"}`}
            </button>
        </div>
      </div>}
    </div>
  );
}
