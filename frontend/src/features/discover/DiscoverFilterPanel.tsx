import { useEffect, useRef, useState } from "react";
import { ALL_VALUE, DiscoverFilterDropdown, type FilterOption } from "./DiscoverFilterDropdown";
import { cn } from "@/lib/utils";

export interface DiscoverFilters {
  topics: string[];
  colleges: string[];
  year: string;
  ipType: string;
  recordType: string;
}

export const EMPTY_FILTERS: DiscoverFilters = {
  topics: [],
  colleges: [],
  year: ALL_VALUE,
  ipType: ALL_VALUE,
  recordType: ALL_VALUE,
};

interface DiscoverFilterPanelProps {
  filters: DiscoverFilters;
  onChange: (next: DiscoverFilters) => void;
  onClear: () => void;
  activeCount: number;
  topicOptions: FilterOption[];
  collegeOptions: FilterOption[];
  yearOptions: FilterOption[];
  ipTypeOptions: FilterOption[];
  recordTypeOptions: FilterOption[];
  loading?: boolean;
  /** Lets the composer's "+" open the same panel — one filter surface, two entry points. */
  openSignal?: number;
}

export function DiscoverFilterPanel({
  filters,
  onChange,
  onClear,
  activeCount,
  topicOptions,
  collegeOptions,
  yearOptions,
  ipTypeOptions,
  recordTypeOptions,
  loading = false,
  openSignal = 0,
}: DiscoverFilterPanelProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const firstSignal = useRef(openSignal);

  useEffect(() => {
    if (openSignal !== firstSignal.current) setOpen(true);
  }, [openSignal]);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const set = <K extends keyof DiscoverFilters>(key: K, value: DiscoverFilters[K]) =>
    onChange({ ...filters, [key]: value });

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={cn(
          "flex items-center gap-2 px-3.5 py-2 rounded-full border text-[13px] font-semibold transition",
          activeCount > 0
            ? "bg-brand-50 border-brand-200 text-brand"
            : "bg-white border-stone-200 text-stone-700 hover:border-stone-300",
        )}
      >
        <i className="fas fa-sliders text-[12px]" />
        <span>Filter</span>
        {activeCount > 0 && (
          <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-brand text-white text-[10px] font-bold flex items-center justify-center">
            {activeCount}
          </span>
        )}
        <i className={cn("fas fa-chevron-down text-[9px] opacity-60 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-2 w-[min(92vw,26rem)] bg-white rounded-2xl shadow-card-md border border-stone-200 z-40">
          <div className="flex items-center justify-between px-4 py-3 border-b border-stone-100">
            <h3 className="text-[13px] font-bold text-stone-900">Refine results</h3>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1 rounded-md text-stone-400 hover:text-stone-600 hover:bg-stone-100"
              aria-label="Close filters"
            >
              <i className="fas fa-times text-[13px]" />
            </button>
          </div>

          <div className="p-4 space-y-3.5">
            <Field label="Topic">
              <DiscoverFilterDropdown
                multi
                label="Any topic"
                options={topicOptions}
                selected={filters.topics}
                onChange={(v) => set("topics", v)}
                loading={loading}
                emptyHint="No classifications recorded yet."
              />
            </Field>
            <Field label="College">
              <DiscoverFilterDropdown
                multi
                label="Any college"
                options={collegeOptions}
                selected={filters.colleges}
                onChange={(v) => set("colleges", v)}
                loading={loading}
                emptyHint="No colleges found."
              />
            </Field>
            <Field label="Year">
              <DiscoverFilterDropdown
                label="Any year"
                options={yearOptions}
                selected={filters.year}
                onChange={(v) => set("year", v)}
              />
            </Field>
            <Field label="IP type">
              <DiscoverFilterDropdown
                label="Any IP type"
                options={ipTypeOptions}
                selected={filters.ipType}
                onChange={(v) => set("ipType", v)}
              />
            </Field>
            <Field label="Record type">
              <DiscoverFilterDropdown
                label="Any record type"
                options={recordTypeOptions}
                selected={filters.recordType}
                onChange={(v) => set("recordType", v)}
                loading={loading}
              />
            </Field>
          </div>

          <div className="flex items-center justify-between px-4 py-3 border-t border-stone-100">
            <button
              type="button"
              onClick={onClear}
              disabled={activeCount === 0}
              className="text-[12px] font-semibold text-stone-500 hover:text-brand disabled:opacity-40 transition"
            >
              Clear all
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-4 py-1.5 rounded-lg bg-brand hover:bg-brand-light text-white text-[12px] font-bold transition"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-[12px] font-semibold text-stone-500 shrink-0">{label}</span>
      {children}
    </div>
  );
}
