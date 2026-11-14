import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";

/**
 * The columns button at the end of the Review pane's tab row (IR-1094; spec
 * §4.8): a short menu of "<Tab> on the right". The host offers it only on a
 * workspace wide enough to keep the paper its room, and decides what choosing
 * does. One visible button, not a "⋯" on every tab.
 */
export function TabBesideMenu<Id extends string>({ choices, onChoose }: {
  /** Each tab that could open on the right: what the host calls it, and its words. */
  choices: readonly { id: Id; label: string }[];
  onChoose: (id: Id) => void;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    // A click anywhere else closes the menu; focus stays where the click put it.
    const outside = (e: MouseEvent) => {
      if (!menu.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("click", outside);
    return () => document.removeEventListener("click", outside);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    // Tab leaves the menu as a menu does: it closes, and focus moves on.
    if (e.key === "Tab") {
      setOpen(false);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      close();
      return;
    }
    const step = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (step === 0) return;
    e.preventDefault();
    const items = Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    items[(at + step + items.length) % items.length]?.focus();
  };

  return (
    <div className="relative shrink-0">
      <button
        ref={button} type="button" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
        aria-label="Open a tab beside this one" title="Open a tab beside this one"
        onClick={() => setOpen((o) => !o)}
        className={cn("review-control text-stone-600 hover:text-brand", FOCUS_RING)}
      >
        <i className="fas fa-table-columns" aria-hidden />
      </button>
      {open && (
        <div
          ref={menu} id={id} role="menu" aria-label="Open a tab beside this one" onKeyDown={onKeyDown}
          className="absolute right-0 top-full z-30 mt-1 min-w-44 rounded-lg border border-stone-300 bg-overlay p-1 shadow-sm"
        >
          {choices.map(({ id: choice, label }) => (
            <button
              key={choice} type="button" role="menuitem" tabIndex={-1}
              onClick={() => { setOpen(false); onChoose(choice); }}
              className={cn("review-control block w-full text-left text-stone-900 hover:bg-stone-100", FOCUS_RING)}
            >
              {label} on the right
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
