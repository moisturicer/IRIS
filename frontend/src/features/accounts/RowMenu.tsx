import { Fragment, useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

const ITEM_SELECTOR = '[role="menuitem"], [role="menuitemradio"]';

export interface RowMenuItem {
  key: string;
  label: string;
  /** A destructive item: Binding Maroon Dark text with a warning glyph, never a filled button (audit CMP-01, DESIGN.md). */
  danger?: boolean;
  /**
   * One of a set of choices (My Library's Reading status, IR-1311): drawn as
   * a `menuitemradio` with a check when on.
   */
  checked?: boolean;
  /** A hairline above the item, to set a group of choices apart (IR-1311). */
  separatorBefore?: boolean;
  /** A Font Awesome class drawn before the label, e.g. "fa-book-open". */
  icon?: string;
  /** Choices that open beside this item: it becomes a flyout and `onSelect` is not used. */
  submenu?: RowMenuItem[];
  onSelect: () => void;
}

interface RowMenuProps {
  /** Names the trigger and the menu, so each row's menu is told apart: "Actions for Ada Lovelace". */
  label: string;
  items: RowMenuItem[];
  /** A smaller trigger in the review pane's split layout, where rows are tight (IR-1192). */
  compact?: boolean;
  /**
   * A 32px trigger for a dense list such as Ask IRIS's conversations (IR-1253),
   * still 44px on a touch screen.
   */
  small?: boolean;
  /**
   * A full-width outlined button reading "More actions", for a phone card's one
   * action (IR-1291). The name stays `label`, which starts with those words.
   */
  wide?: boolean;
  /** Three dots stacked, for the end of a list row; the default lies them in a line. */
  vertical?: boolean;
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
export function RowMenu({ label, items, compact = false, small = false, wide = false, vertical = false }: RowMenuProps) {
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
    if (open && anchor) menuRef.current?.querySelector<HTMLButtonElement>(ITEM_SELECTOR)?.focus();
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
    const buttons = Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>(ITEM_SELECTOR) ?? []);
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
        className={cn(
          wide
            ? "inline-flex min-h-11 w-full items-center justify-center rounded-full border border-stone-300 px-4 text-control font-medium text-stone-700 transition-colors duration-150 hover:bg-stone-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand aria-expanded:bg-stone-50 motion-reduce:transition-none"
            : "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-stone-600 transition-colors duration-150 hover:bg-stone-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand aria-expanded:bg-stone-100 motion-reduce:transition-none",
          // 36px in the split layout, as the review pane's other controls (`reading-split:min-h-9`).
          compact && "-my-2 -mr-2 reading-split:h-9 reading-split:w-9",
          small && "h-8 w-8 touch:h-11 touch:w-11",
        )}
      >
        {wide ? "More actions" : (
          <svg viewBox="0 0 24 24" fill="currentColor" className={compact || small ? "h-4 w-4" : "h-5 w-5"} aria-hidden="true">
            {vertical ? (
              <>
                <circle cx="12" cy="5" r="1.8" />
                <circle cx="12" cy="12" r="1.8" />
                <circle cx="12" cy="19" r="1.8" />
              </>
            ) : (
              <>
                <circle cx="5" cy="12" r="1.8" />
                <circle cx="12" cy="12" r="1.8" />
                <circle cx="19" cy="12" r="1.8" />
              </>
            )}
          </svg>
        )}
      </button>
      {open && anchor && createPortal(
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKeyDown}
          style={{ top: anchor.top, right: anchor.right }}
          className="fixed z-40 min-w-52 rounded-card border border-stone-200 bg-overlay p-1.5 shadow-card-md"
        >
          {items.map((item) => (
            <Fragment key={item.key}>
              {item.separatorBefore && <div role="separator" className="mx-2 my-1 border-t border-stone-200" />}
              {item.submenu ? (
                <SubmenuItem item={item} onChoose={(choice) => { closeToTrigger(); choice.onSelect(); }} />
              ) : (
                <MenuButton
                  item={item}
                  onClick={() => {
                    closeToTrigger();
                    item.onSelect();
                  }}
                />
              )}
            </Fragment>
          ))}
        </div>,
        document.body,
      )}
    </>
  );
}

const ITEM_CLASS =
  "flex min-h-11 w-full items-center gap-3 rounded-control px-3 text-left text-sm transition-colors duration-150 hover:bg-brand/[0.07] focus-visible:bg-brand/[0.07] focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand motion-reduce:transition-none";

function MenuButton({ item, onClick }: { item: RowMenuItem; onClick: () => void }) {
  const icon = item.danger ? "fa-triangle-exclamation" : item.icon;
  return (
    <button
      type="button"
      role={item.checked === undefined ? "menuitem" : "menuitemradio"}
      aria-checked={item.checked}
      onClick={onClick}
      className={cn(ITEM_CLASS, item.danger ? "text-brand-dark" : "text-stone-800", item.checked && "font-semibold text-stone-900")}
    >
      {icon && <i className={cn("fas w-4 shrink-0 text-center text-label", icon, !item.danger && "text-stone-500")} aria-hidden />}
      <span className="min-w-0 flex-1">{item.label}</span>
      {item.checked && <i className="fas fa-check shrink-0 text-label text-brand" aria-hidden />}
    </button>
  );
}

/** The flyout's width with its gap: what has to fit beside the menu. */
const FLYOUT_PX = 200;

/**
 * An item that opens its choices in a card beside it, on hover, press or the
 * right arrow. The card goes right, or left when the window ends first, or,
 * on a phone with room on neither side, under the item.
 */
function SubmenuItem({ item, onChoose }: { item: RowMenuItem; onChoose: (item: RowMenuItem) => void }) {
  const [side, setSide] = useState<"right" | "left" | "below" | null>(null);
  const subId = useId();
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  /** Opened from the keyboard, so the first choice takes focus. */
  const focusFirst = useRef(false);
  const open = side !== null;

  const show = () => {
    const rect = wrap.current?.getBoundingClientRect();
    if (!rect) return;
    setSide(rect.right + FLYOUT_PX <= window.innerWidth ? "right" : rect.left >= FLYOUT_PX ? "left" : "below");
  };
  const focusChoice = () => card.current?.querySelector<HTMLButtonElement>(ITEM_SELECTOR)?.focus();
  useEffect(() => {
    if (!open || !focusFirst.current) return;
    focusFirst.current = false;
    focusChoice();
  }, [open]);

  return (
    <div
      ref={wrap}
      className="relative"
      onMouseEnter={show}
      onMouseLeave={() => setSide(null)}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" && e.target === trigger.current) {
          e.preventDefault();
          e.stopPropagation();
          if (open) focusChoice();
          else { focusFirst.current = true; show(); }
        } else if (open && (e.key === "ArrowLeft" || e.key === "Escape")) {
          e.preventDefault();
          e.stopPropagation();
          setSide(null);
          trigger.current?.focus();
        }
      }}
    >
      <button
        ref={trigger}
        type="button"
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? subId : undefined}
        onClick={(e) => {
          // `detail` is 0 for Enter or Space.
          if (e.detail === 0 && open) focusChoice();
          else { focusFirst.current = e.detail === 0; show(); }
        }}
        className={cn(ITEM_CLASS, "text-stone-800", open && "bg-brand/[0.07]")}
      >
        {item.icon && <i className={cn("fas w-4 shrink-0 text-center text-label text-stone-500", item.icon)} aria-hidden />}
        <span className="min-w-0 flex-1">{item.label}</span>
        <i className={cn("fas shrink-0 text-2xs text-stone-500", side === "below" ? "fa-chevron-down" : "fa-chevron-right")} aria-hidden />
      </button>
      {open && (
        // Padding, not a margin: the pointer crosses to the card without leaving the item.
        <div className={cn(side === "below" ? "pl-4" : "absolute -top-1.5 z-10", side === "right" && "left-full pl-2", side === "left" && "right-full pr-2")}>
          <div
            ref={card}
            id={subId}
            role="menu"
            aria-label={item.label}
            className={cn("min-w-44", side !== "below" && "rounded-card border border-stone-200 bg-overlay p-1.5 shadow-card-md")}
          >
            {item.submenu!.map((choice) => (
              <MenuButton key={choice.key} item={choice} onClick={() => onChoose(choice)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
