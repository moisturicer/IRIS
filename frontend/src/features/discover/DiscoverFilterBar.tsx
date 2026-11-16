import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";

import { useDialogFocus } from "@/hooks/useDialogFocus";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { PILL_PRIMARY, PILL_SECONDARY } from "@/components/ui/pillStyles";
import { cn } from "@/lib/utils";
import { ALL_VALUE, DiscoverFilterDropdown, type FilterOption } from "./DiscoverFilterDropdown";
import { SELECTED } from "@/components/ui/highlightRoles";

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
  /** Year completed, from and to; either end may be open (IR-947). */
  yearFrom:        string;
  yearTo:          string;
  ip:              string;
}

export const EMPTY_FILTERS: DiscoverFilters = {
  recordType: ALL_VALUE,
  colleges: [],
  classifications: [],
  yearFrom: ALL_VALUE,
  yearTo: ALL_VALUE,
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
  options:   DiscoverFilterOptions;
  /** Reference data still loading: the lists say so rather than look empty. */
  loading:   boolean;
  /** How many results the current filters return, for the sheet's button. */
  resultCount: number | null;
  /** The reader's Areas, drawn below the filters (IR-1188). Given the panel's
   *  close, for a save or reset that finishes there. Omitted, no section. */
  areas?: (close: () => void) => ReactNode;
}

/** Both ends set, and the From after the To. "Any year" never conflicts. */
export function endsBeforeItStarts(from: string, to: string): boolean {
  return from !== ALL_VALUE && to !== ALL_VALUE && Number(from) > Number(to);
}

/**
 * `filters` with one end of the year range set (IR-947). A range never ends
 * before it starts: choosing a From after the To moves the To up to it, and a
 * To before the From moves the From down, so one year is From and To alike.
 */
export function withYear(filters: DiscoverFilters, end: "yearFrom" | "yearTo", value: string): DiscoverFilters {
  const next = { ...filters, [end]: value };
  if (endsBeforeItStarts(next.yearFrom, next.yearTo)) {
    if (end === "yearFrom") next.yearTo = value;
    else next.yearFrom = value;
  }
  return next;
}

/** The year range counts as one filter, however many of its ends are set. */
export function activeFilterCount(filters: DiscoverFilters): number {
  return (
    filters.colleges.length +
    filters.classifications.length +
    (filters.recordType !== ALL_VALUE ? 1 : 0) +
    (filters.yearFrom !== ALL_VALUE || filters.yearTo !== ALL_VALUE ? 1 : 0) +
    (filters.ip !== ALL_VALUE ? 1 : 0)
  );
}

/**
 * One Filters control keeps the feed toolbar compact at every width. Its panel
 * holds every catalogue filter, each with a visible label, and below them the
 * reader's Areas (IR-1188). Sort is not here: it sits beside it (IR-1187).
 *
 * The panel is modal while open: Tab stays inside, Escape closes it, and focus
 * goes back to the Filters control (`useDialogFocus`, shared with `Modal`).
 */
export function DiscoverFilterBar({
  className,
  filters,
  onChange,
  options,
  loading,
  resultCount,
  areas,
}: DiscoverFilterBarProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const filtersHeadingId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const count = activeFilterCount(filters);
  const close = useCallback(() => setOpen(false), []);

  // Focus moves to the panel's first control (Close) and back to the trigger.
  useDialogFocus(open, panelRef, close, triggerRef.current);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const set = <K extends keyof DiscoverFilters>(key: K, value: DiscoverFilters[K]) =>
    onChange({ ...filters, [key]: value });
  const setYear = (end: "yearFrom" | "yearTo", value: string) => onChange(withYear(filters, end, value));

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
          name="Year from"
          options={options.years}
          selected={filters.yearFrom}
          onChange={(v) => setYear("yearFrom", v)}
        />
        <DiscoverFilterDropdown
          {...shared}
          name="Year to"
          options={options.years}
          selected={filters.yearTo}
          onChange={(v) => setYear("yearTo", v)}
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
            "relative inline-flex h-11 px-3 items-center justify-center gap-2 rounded-control border text-small font-medium",
            COLOUR_TRANSITION,
            FOCUS_RING,
            count > 0 ? SELECTED : "bg-white border-stone-300 text-stone-700",
          )}
        >
          <i className="fas fa-sliders text-label" aria-hidden />
          <span>Filters</span>
          {/* A real space: the button is a flex row, which draws none, but the
              visible text a checker compares with the name reads "Filters1"
              without it (IR-934, WCAG 2.5.3). */}
          {" "}
          {count > 0 && (
            <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-brand text-white text-label font-semibold flex items-center justify-center">
              {count}
              <span className="sr-only"> active</span>
            </span>
          )}
        </button>

      {open && <div id={panelId} ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="Filters"
        className="fixed inset-x-4 bottom-4 z-50 flex max-h-[min(80dvh,40rem)] flex-col overflow-x-hidden rounded-card border border-stone-200 bg-white shadow-card-md focus:outline-none sm:absolute sm:inset-x-auto sm:bottom-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[24rem]">
        <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3">
          <h2 className="text-small font-semibold text-stone-900">Filters</h2>
          <button type="button" onClick={close} aria-label="Close filters"
            className={cn("flex h-9 w-9 items-center justify-center rounded-control text-stone-600 hover:bg-stone-100", FOCUS_RING)}>
            <i className="fas fa-xmark text-small" aria-hidden />
          </button>
        </div>
        <div className="flex min-w-0 flex-col gap-5 overflow-y-auto px-4 py-4">
          <section aria-labelledby={filtersHeadingId} className="flex min-w-0 flex-col gap-3">
            <h3 id={filtersHeadingId} className="text-small font-semibold text-stone-900">Filter the list</h3>
            {controls()}
          </section>
          {areas && <div className="border-t border-stone-100 pt-4">{areas(close)}</div>}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-stone-100 px-4 py-3">
            <button
              type="button"
              onClick={() => onChange(EMPTY_FILTERS)}
              disabled={count === 0}
              className={cn(PILL_SECONDARY, "disabled:opacity-50 disabled:pointer-events-none")}
            >
              Clear filters
            </button>
            <button type="button" onClick={close} className={PILL_PRIMARY}>
              {resultCount === null ? "Show results" : `Show ${resultCount} result${resultCount === 1 ? "" : "s"}`}
            </button>
        </div>
      </div>}
    </div>
  );
}
