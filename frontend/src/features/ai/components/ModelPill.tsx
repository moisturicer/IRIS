import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

export interface ModelPillOption<T extends string> {
  value: T;
  /** The short name on the pill. */
  short: string;
  label: string;
  description: string;
  icon: string;
}

interface ModelPillProps<T extends string> {
  /** What the pill chooses, for its accessible name. */
  name: string;
  value: T;
  options: readonly ModelPillOption<T>[];
  onChange?: (value: T) => void;
  note?: string;
}

/** The composer's answer setting: a pill that opens a short menu above itself. */
export function ModelPill<T extends string>({ name, value, options, onChange, note }: ModelPillProps<T>) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const current = options.find((option) => option.value === value) ?? options[0];

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };

  const onMenuKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "Tab") {
      setOpen(false);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const items = [...(menu.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? [])];
      const step = event.key === "ArrowDown" ? 1 : -1;
      const from = items.indexOf(document.activeElement as HTMLElement);
      items[(from + step + items.length) % items.length]?.focus();
    }
  };

  return (
    <div ref={root} className="relative">
      <button
        ref={trigger}
        type="button"
        aria-label={`${name}: ${current.short}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((was) => !was)}
        className={cn(
          "inline-flex min-h-11 items-center gap-1.5 rounded-full bg-stone-100 px-3 text-small font-medium text-stone-700 hover:bg-stone-200 hover:text-stone-900 [@media(pointer:fine)]:min-h-9",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
      >
        <i className={cn(current.icon, "text-xs")} aria-hidden />
        {current.short}
        <i className={cn("fas fa-chevron-up text-[10px] transition-transform duration-150 motion-reduce:transition-none", open || "rotate-180")} aria-hidden />
      </button>

      {open && (
        <div
          ref={menu}
          id={menuId}
          role="menu"
          aria-label={name}
          onKeyDown={onMenuKey}
          className="absolute bottom-full left-0 z-30 mb-2 w-72 max-w-[calc(100vw-3rem)] rounded-xl border border-stone-200 bg-surface p-1.5 text-left shadow-card-md motion-safe:animate-fade-in"
        >
          {options.map((option) => {
            const selected = option.value === value;
            return (
              <button
                key={option.value}
                type="button"
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => {
                  onChange?.(option.value);
                  close();
                }}
                className={cn(
                  "flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left",
                  selected ? "bg-brand-50 text-brand" : "text-stone-800 hover:bg-stone-100",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                )}
              >
                <i className={cn(option.icon, "mt-1 w-4 text-center text-sm")} aria-hidden />
                <span className="min-w-0">
                  <span className="block text-small font-semibold">{option.label}</span>
                  <span className={cn("block text-small", selected ? "text-brand" : "text-stone-600")}>{option.description}</span>
                </span>
              </button>
            );
          })}
          {note && <p className="mt-1.5 border-t border-stone-200 px-3 pb-1 pt-2 text-2xs text-stone-600">{note}</p>}
        </div>
      )}
    </div>
  );
}
