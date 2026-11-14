import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";

interface TooltipProps {
  /** What the tooltip says. The wrapped control keeps its own accessible name. */
  label: string;
  /** Show nothing: the label is already on screen, or the control is open. */
  disabled?: boolean;
  /** Classes for the wrapper, e.g. `block` to wrap a full-width link. */
  className?: string;
  children: ReactNode;
}

/**
 * A label beside a control whose own text is hidden, such as an icon rail
 * button (IR-1086).
 *
 * Shown on hover and on keyboard focus, hidden again on leave, blur or Escape
 * (WCAG 1.4.13: dismissable, and hoverable -- the tip is drawn flush against
 * the control, so the pointer can cross onto it). It is a visual aid only: it
 * is not an `aria-describedby`, so a screen reader that already reads the
 * control's name does not hear it twice. It is drawn in a portal at the
 * control's right edge, because the rail's nav scrolls and would clip it.
 */
export function Tooltip({ label, disabled = false, className, children }: TooltipProps) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);
  const wrapperRef = useRef<HTMLSpanElement>(null);
  // Focus that arrives with a mouse press is not keyboard focus: a click would
  // otherwise leave the tooltip stuck on screen until the control blurs.
  const pressing = useRef(false);
  const open = !disabled && !dismissed && (hovered || focused);

  useLayoutEffect(() => {
    if (!open || !wrapperRef.current) {
      setAnchor(null);
      return;
    }
    const rect = wrapperRef.current.getBoundingClientRect();
    setAnchor({ top: rect.top + rect.height / 2, left: rect.right });
  }, [open]);

  // The tip is placed once, when it opens. A scroll or a resize would leave it
  // beside the wrong place, so either one closes it instead.
  useEffect(() => {
    if (!open) return;
    const close = () => setDismissed(true);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  return (
    <span
      ref={wrapperRef}
      className={cn("relative", className)}
      // A mouse pointer only: a tap on a touch screen also fires enter, and
      // would leave the tip up after the link it just followed.
      onPointerEnter={(e) => { if (e.pointerType === "mouse") setHovered(true); }}
      onPointerLeave={() => { setHovered(false); setDismissed(false); pressing.current = false; }}
      onMouseDown={() => { pressing.current = true; }}
      onMouseUp={() => { pressing.current = false; }}
      onFocus={() => { if (!pressing.current) setFocused(true); }}
      onBlur={() => { setFocused(false); setDismissed(false); }}
      onKeyDown={(e) => { if (e.key === "Escape" && open) setDismissed(true); }}
    >
      {children}
      {open && anchor && createPortal(
        // `pl-2` is part of the tooltip, so the gap between it and the control
        // is still hover; the visible bubble is the inner span.
        <span
          className="pointer-events-auto fixed z-[60] -translate-y-1/2 pl-2"
          style={{ top: anchor.top, left: anchor.left }}
        >
          <span
            role="tooltip"
            className="block whitespace-nowrap rounded-md bg-stone-900 px-2.5 py-1.5 text-xs font-medium text-white shadow-card-md animate-fade-in motion-reduce:animate-none"
          >
            {label}
          </span>
        </span>,
        document.body,
      )}
    </span>
  );
}
