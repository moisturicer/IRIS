import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

import { FOCUS_RING } from "./interaction";

interface InfoHintProps {
  /** The text's element id, so a control can name it in `aria-describedby`. */
  id: string;
  /** What the hint is about, for the button's name: "About Keywords". */
  about: string;
  children: string;
  className?: string;
}

const WIDTH = 256;
const GAP = 8;

/**
 * A "?" that shows a field's hint on hover or keyboard focus, in place of a
 * line of small text under the field. The tip is drawn in a portal at fixed
 * coordinates, so a scrolling column or a dialog's edge never clips it, and it
 * stays inside the window. The text stays in the page (hidden, not removed),
 * so `aria-describedby` still reads it.
 */
export function InfoHint({ id, about, children, className }: InfoHintProps) {
  const [open, setOpen] = useState(false);
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  const button = useRef<HTMLButtonElement>(null);
  const tip = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    if (!open || !button.current) { setAt(null); return; }
    const rect = button.current.getBoundingClientRect();
    const left = Math.max(GAP, Math.min(rect.left - 12, window.innerWidth - WIDTH - GAP));
    const height = tip.current?.offsetHeight ?? 0;
    // Below the icon, or above it when the window ends first.
    const below = rect.bottom + 6;
    const top = below + height > window.innerHeight - GAP ? Math.max(GAP, rect.top - 6 - height) : below;
    setAt({ top, left });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    // Escape closes the tip first, not the dialog behind it.
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  return (
    <span className={cn("inline-flex", className)}>
      <button
        ref={button}
        type="button"
        aria-label={`About ${about}`}
        aria-describedby={id}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className={cn(
          "inline-flex size-5 items-center justify-center rounded-full text-stone-500 transition-colors duration-150 hover:bg-brand/[0.07] hover:text-brand-dark motion-reduce:transition-none",
          FOCUS_RING,
        )}
      >
        <i className="fas fa-circle-question text-small" aria-hidden />
      </button>
      {/* In the page but out of sight, for `aria-describedby`. */}
      <span id={id} className="sr-only">{children}</span>
      {open && createPortal(
        <span
          ref={tip}
          aria-hidden
          style={{ top: at?.top ?? 0, left: at?.left ?? 0, width: WIDTH, visibility: at ? "visible" : "hidden" }}
          className="pointer-events-none fixed z-[70] rounded-control border border-stone-200 bg-overlay px-3 py-2 text-small font-normal leading-snug text-stone-700 shadow-card-md"
        >
          {children}
        </span>,
        document.body,
      )}
    </span>
  );
}
