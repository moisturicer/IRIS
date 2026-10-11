import { useEffect, useRef, useState } from "react";

import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
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
  /**
   * What the control filters, e.g. "Type". It is always the start of the
   * button's text, so the button keeps its name whatever is chosen, and the
   * visible text and the accessible name are the same words.
   */
  name: string;
  options: FilterOption[];
  /** Shown in place of the list while reference data is still loading. */
  loading?: boolean;
  /** Shown when the endpoint returned nothing. */
  emptyHint?: string;
  /**
   * The list opens in the flow under the button rather than floating over the
   * page. For the filter sheet, whose scrolling body would clip a popover.
   */
  inline?: boolean;
  /** Never drawn as "active": for Sort, which always has a value. */
  neutral?: boolean;
  /** Stretch to the container's width, for the stacked sheet layout. */
  block?: boolean;
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
  const { name, options, loading = false, emptyHint, inline = false, neutral = false, block = false } = props;
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
      // Close this list only. In the filter sheet the same Escape would also
      // close the dialog; catching it first keeps one key press to one closing.
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown, true);
    };
  }, [open]);

  const isActive =
    !neutral &&
    (props.multi ? props.selected.length > 0 : props.selected !== ALL_VALUE && props.selected !== "");

  const chosenLabel = !props.multi
    ? options.find((o) => o.value === props.selected && o.value !== ALL_VALUE)?.label
    : undefined;

  return (
    <div className={cn("relative", block && "w-full")} ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={cn(
          "inline-flex items-center gap-1.5 min-h-[36px] px-3.5 py-1.5 rounded-full border text-small font-medium",
          COLOUR_TRANSITION,
          FOCUS_RING,
          block ? "w-full justify-between" : "max-w-[18rem]",
          isActive
            ? "bg-brand-50 border-brand text-brand"
            : "bg-white text-stone-700 border-stone-300 hover:border-stone-500",
        )}
      >
        <span className="truncate">{chosenLabel ? `${name}: ${chosenLabel}` : name}</span>

        {props.multi && props.selected.length > 0 && (
          <span className="min-w-[18px] h-[18px] px-1 shrink-0 rounded-full bg-brand text-white text-label font-semibold flex items-center justify-center">
            {props.selected.length}
          </span>
        )}
        <i
          className={cn(
            "fas fa-chevron-down text-[10px] text-stone-500 shrink-0 transition-transform motion-reduce:transition-none",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>

      {open && (
        <div
          role="listbox"
          // A listbox needs its own accessible name (axe: aria-input-field-name).
          aria-label={name}
          aria-multiselectable={props.multi || undefined}
          className={cn(
            "max-h-64 overflow-y-auto bg-white rounded-xl border border-stone-200 py-1.5",
            inline ? "mt-2 w-full" : "absolute left-0 top-full mt-2 w-64 shadow-card-md z-50",
          )}
        >
          {loading ? (
            <p className="px-3 py-2 text-small text-stone-600">Loading…</p>
          ) : options.length === 0 ? (
            <p className="px-3 py-2 text-small text-stone-600">{emptyHint ?? "No options available."}</p>
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
                  className={cn(
                    "w-full flex items-center justify-between gap-2 px-3 py-2 text-small text-stone-800 text-left hover:bg-stone-50",
                    COLOUR_TRANSITION,
                    FOCUS_RING,
                  )}
                >
                  <span className="truncate">{option.label}</span>
                  {selected && <i className="fas fa-check text-brand text-[12px] shrink-0" aria-hidden />}
                </button>
              );
            })
          )}

          {props.multi && props.selected.length > 0 && (
            <div className="border-t border-stone-100 mt-1 pt-1">
              <button
                type="button"
                onClick={() => props.onChange([])}
                className={cn(
                  "w-full px-3 py-2 text-left text-small font-medium text-stone-600 hover:text-brand",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                )}
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
