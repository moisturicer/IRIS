import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { ChevronUpIcon, type OutlineIcon } from "./AskIrisIcons";

export interface ModelPillOption<T extends string> {
  value: T;
  /** The short name on the pill. */
  short: string;
  label: string;
  description: string;
  /** One of the Ask IRIS outline icons. */
  icon: OutlineIcon;
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
          "inline-flex min-h-11 items-center gap-1.5 rounded-full bg-stone-100 px-3 text-control font-medium text-stone-700 hover:bg-stone-200 hover:text-stone-900 [@media(pointer:fine)]:min-h-9",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
      >
        <current.icon inline />
        {current.short}
        <ChevronUpIcon inline className={cn("transition-transform duration-150 motion-reduce:transition-none", open || "rotate-180")} />
      </button>

      {open && (
        <div
          ref={menu}
          id={menuId}
          role="menu"
          aria-label={name}
          onKeyDown={onMenuKey}
          className="absolute bottom-full left-0 z-30 mb-2 w-72 max-w-[calc(100vw-3rem)] rounded-card border border-stone-200 bg-surface p-1.5 text-left shadow-card-md motion-safe:animate-fade-in"
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
                  "flex w-full items-start gap-3 rounded-control px-3 py-2 text-left",
                  selected ? "bg-surface text-stone-900 ring-1 ring-inset ring-stone-900" : "text-stone-800 hover:bg-stone-100",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                )}
              >
                <option.icon inline className="mt-1" />
                <span className="min-w-0">
                  <span className="block text-control font-semibold">{option.label}</span>
                  <span className={cn("block text-small", selected ? "text-brand" : "text-stone-600")}>{option.description}</span>
                </span>
              </button>
            );
          })}
          {note && <p className="mt-1.5 border-t border-stone-200 px-3 pb-1 pt-2 text-small text-stone-600">{note}</p>}
        </div>
      )}
    </div>
  );
}
