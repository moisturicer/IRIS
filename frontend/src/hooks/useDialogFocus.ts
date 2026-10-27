import { useEffect, useRef, type RefObject } from "react";
import { nextTrapFocus, tabbableWithin } from "@/lib/focusTrap";

/**
 * The keyboard half of a modal surface: Escape closes it, focus moves in on
 * open, Tab stays inside, and focus goes back to whatever opened it on close
 * (IR-158). Shared by `Modal` and Ask IRIS's phone drawers (IR-570), so the
 * two cannot drift apart.
 *
 * `panelRef` should carry `tabIndex={-1}`, so a panel of pure text still
 * takes focus and Escape.
 *
 * `returnTo` names where focus goes back to when the opener cannot be read
 * off the page at open: a surface that makes the rest of the page inert in
 * the same render as it opens loses the opener's focus before this runs, so
 * its caller records the opener when it is activated (IR-570).
 */
export function useDialogFocus(
  open: boolean,
  panelRef: RefObject<HTMLElement>,
  onClose: () => void,
  returnTo?: HTMLElement | null,
) {
  // The element that had focus when the dialog opened. Without it, closing
  // drops focus to <body> and a keyboard user restarts from the top.
  const triggerRef = useRef<HTMLElement | null>(null);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Move focus into the panel on open, and restore it to the trigger on close.
  useEffect(() => {
    if (!open) return;

    const active = document.activeElement;
    // Opened programmatically, <body> is the active element; recording it
    // would make the restore a silent no-op that looks like it worked.
    triggerRef.current =
      returnTo ?? (active instanceof HTMLElement && active !== document.body ? active : null);

    const panel = panelRef.current;
    if (panel) {
      const [first] = tabbableWithin(panel);
      (first ?? panel).focus();
    }

    return () => {
      // A trigger the dialog unmounted cannot take focus back; focusing a
      // detached node sends it to <body>, the bug this restore exists to stop.
      const trigger = triggerRef.current;
      if (trigger && trigger.isConnected) trigger.focus();
      triggerRef.current = null;
    };
    // `returnTo` is read once, at open, like the active element it stands in for.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, panelRef]);

  // Keep Tab inside the panel.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const panel = panelRef.current;
      if (!panel) return;

      const focusables = tabbableWithin(panel);
      const current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const next = nextTrapFocus(focusables, current, e.shiftKey);
      // Nothing to trap onto: let Tab through rather than strand the user.
      if (!next) return;

      e.preventDefault();
      next.focus();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, panelRef]);
}
