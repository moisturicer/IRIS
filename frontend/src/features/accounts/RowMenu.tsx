import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

export interface RowMenuItem {
  key: string;
  label: string;
  /** A destructive item: maroon text, never a filled button (audit CMP-01). */
  danger?: boolean;
  onSelect: () => void;
}

interface RowMenuProps {
  /** Names the trigger and the menu, so each row's menu is told apart: "Actions for Ada Lovelace". */
  label: string;
  items: RowMenuItem[];
}

/**
 * A row's "⋯" actions menu (IR-1077).
 *
 * Opens onto its first item; the arrow keys, Home and End move between items;
 * Escape, Tab, a click elsewhere, a scroll or a resize close it. Choosing an
 * item closes the menu and puts focus on the trigger first, so a dialog the
 * item opens returns focus to a control that still exists. The list is drawn
 * in a portal at the trigger's edge, because the table clips what overflows it.
 * Renders nothing when there is nothing to offer.
 */
export function RowMenu({ label, items }: RowMenuProps) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<{ top: number; right: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setAnchor(null);
      return;
    }
    const rect = triggerRef.current.getBoundingClientRect();
    setAnchor({ top: rect.bottom + 4, right: window.innerWidth - rect.right });
  }, [open]);

  // The first item takes focus once the list is drawn.
  useEffect(() => {
    if (open && anchor) menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
  }, [open, anchor]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const close = () => setOpen(false);
    document.addEventListener("mousedown", onPointer);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  if (items.length === 0) return null;

  const closeToTrigger = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const buttons = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []);
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const move = (index: number) => {
      event.preventDefault();
      buttons[(index + buttons.length) % buttons.length]?.focus();
    };
    switch (event.key) {
      case "ArrowDown": move(at + 1); break;
      case "ArrowUp":   move(at - 1); break;
      case "Home":      move(0); break;
      case "End":       move(buttons.length - 1); break;
      case "Escape":
      case "Tab":
        event.preventDefault();
        closeToTrigger();
        break;
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-11 w-11 items-center justify-center rounded-full text-stone-600 transition-colors duration-150 hover:bg-stone-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand aria-expanded:bg-stone-100 motion-reduce:transition-none"
      >
        <svg viewBox="0 0 24 24" fill="currentColor" className="h-[18px] w-[18px]" aria-hidden="true">
          <circle cx="5" cy="12" r="1.8" />
          <circle cx="12" cy="12" r="1.8" />
          <circle cx="19" cy="12" r="1.8" />
        </svg>
      </button>
      {open && anchor && createPortal(
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKeyDown}
          style={{ top: anchor.top, right: anchor.right }}
          className="fixed z-40 min-w-44 rounded-xl border border-stone-200 bg-overlay p-1 shadow-card-md"
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              onClick={() => {
                closeToTrigger();
                item.onSelect();
              }}
              className={cn(
                "block min-h-11 w-full rounded-lg px-3 text-left text-sm hover:bg-stone-100 focus-visible:bg-stone-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand",
                item.danger ? "text-brand" : "text-stone-800",
              )}
            >
              {item.label}
            </button>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}
