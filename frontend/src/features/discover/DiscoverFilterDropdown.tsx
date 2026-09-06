import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * An option always carries the stable value the API expects (`value`) plus the
 * label a human reads. Options are supplied by the caller — the page builds
 * them from reference-data endpoints, so nothing here is hard-coded.
 */
export interface FilterOption {
  value: string;
  label: string;
}

interface BaseProps {
  label: string;
  icon?: string;
  options: FilterOption[];
  /** Shown in place of the list while reference data is still loading. */
  loading?: boolean;
  /** Shown when the endpoint returned nothing. */
  emptyHint?: string;
}

interface SingleProps extends BaseProps {
  multi?: false;
  selected: string;
  onChange: (value: string) => void;
}

interface MultiProps extends BaseProps {
  multi: true;
  selected: string[];
  onChange: (value: string[]) => void;
}

type DiscoverFilterDropdownProps = SingleProps | MultiProps;

/** Single-select uses this sentinel for "no filter applied". */
export const ALL_VALUE = "all";

export function DiscoverFilterDropdown(props: DiscoverFilterDropdownProps) {
  const { label, icon, options, loading = false, emptyHint } = props;
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  const isActive = props.multi
    ? props.selected.length > 0
    : props.selected !== ALL_VALUE && props.selected !== "";

  const activeLabel = !props.multi
    ? options.find((o) => o.value === props.selected)?.label
    : undefined;

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={cn(
          "flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition cursor-pointer max-w-[16rem]",
          isActive
            ? "bg-brand-50 border-brand text-brand"
            : "bg-white text-stone-700 border-stone-200 hover:border-stone-300",
        )}
      >
        {icon && <i className={cn("fas", icon, "text-[10px] shrink-0")} aria-hidden />}
        <span className="truncate">{isActive && activeLabel ? activeLabel : label}</span>

        {props.multi && props.selected.length > 0 && (
          <span className="min-w-[16px] h-4 px-1 shrink-0 rounded-full bg-brand text-white text-[10px] font-bold flex items-center justify-center">
            {props.selected.length}
          </span>
        )}
        <i className={cn("fas fa-chevron-down text-[8px] opacity-60 ml-0.5 shrink-0 transition-transform", open && "rotate-180")} aria-hidden />
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute left-0 top-full mt-1.5 w-60 max-h-64 overflow-y-auto bg-white rounded-lg shadow-card-md border border-slate-200 py-1.5 z-50"
        >
          {loading ? (
            <p className="px-3 py-2 text-[12px] text-slate-400">Loading…</p>
          ) : options.length === 0 ? (
            <p className="px-3 py-2 text-[12px] text-slate-400">
              {emptyHint ?? "No options available."}
            </p>
          ) : (
            options.map((option) => {
              const selected = props.multi
                ? props.selected.includes(option.value)
                : props.selected === option.value;

              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => {
                    if (props.multi) {
                      props.onChange(
                        selected
                          ? props.selected.filter((v) => v !== option.value)
                          : [...props.selected, option.value],
                      );
                    } else {
                      props.onChange(option.value);
                      setOpen(false);
                    }
                  }}
                  className="w-full flex items-center justify-between gap-2 px-3 py-1.5 text-[12px] text-slate-700 hover:bg-slate-50 transition text-left"
                >
                  <span className="truncate">{option.label}</span>
                  {selected && <i className="fas fa-check text-brand text-[11px] shrink-0" aria-hidden />}
                </button>
              );
            })
          )}

          {props.multi && props.selected.length > 0 && (
            <div className="border-t border-slate-100 mt-1 pt-1">
              <button
                type="button"
                onClick={() => props.onChange([])}
                className="w-full px-3 py-1.5 text-left text-[12px] font-semibold text-slate-500 hover:text-brand transition"
              >
                Clear selection
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
