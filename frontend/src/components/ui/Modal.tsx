import { useEffect, useId, useRef, type ReactNode } from "react";
import { nextTrapFocus, tabbableWithin } from "@/lib/focusTrap";

interface ModalProps {
  open:     boolean;
  onClose:  () => void;
  title?:   string;
  children: ReactNode;
  /** px width class, e.g. "max-w-lg". Defaults to "max-w-lg". */
  size?:    string;
}

export function Modal({ open, onClose, title, children, size = "max-w-lg" }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  // The element that had focus when the dialog opened, so it can be given focus
  // back on close. Without this, closing drops focus to <body> and a keyboard
  // user restarts from the top of the page.
  const triggerRef = useRef<HTMLElement | null>(null);
  // `useId` rather than a literal "modal-title": two dialogs mounted at once
  // (a confirm on top of a form) would otherwise share one id, and
  // `aria-labelledby` would resolve to whichever rendered first.
  const titleId = useId();

  // Close on Escape key
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
    // A modal opened programmatically (a route effect, a toast action) leaves
    // <body> as the active element. Recording it would make the restore a
    // silent no-op -- body.focus() does nothing -- while looking like it worked.
    triggerRef.current =
      active instanceof HTMLElement && active !== document.body ? active : null;

    const panel = panelRef.current;
    if (panel) {
      // Prefer the first real control; fall back to the panel, which carries
      // tabIndex={-1} so a dialog of pure text is still announced and still
      // takes Escape.
      const [first] = tabbableWithin(panel);
      (first ?? panel).focus();
    }

    return () => {
      // `isConnected` guards the case where the trigger itself was unmounted by
      // whatever the dialog did -- focusing a detached node silently sends focus
      // to <body>, which is the bug this restore exists to prevent.
      const trigger = triggerRef.current;
      if (trigger && trigger.isConnected) trigger.focus();
      triggerRef.current = null;
    };
  }, [open]);

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
      // A null target means there is nothing to trap onto; let Tab through
      // rather than stranding the user in a dialog with no exit.
      if (!next) return;

      e.preventDefault();
      next.focus();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Panel */}
      <div
        ref={panelRef}
        tabIndex={-1}
        className={`relative bg-white rounded-xl shadow-xl w-full ${size} max-h-[90vh] flex flex-col outline-none`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
      >
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
            <h2 id={titleId} className="text-[15px] font-semibold text-gray-900">{title}</h2>
            <button
              onClick={onClose}
              className="p-1 rounded-md text-gray-500 hover:text-gray-700 hover:bg-gray-100"
              aria-label="Close"
            >
              <i className="fa fa-times text-[14px]" aria-hidden />
            </button>
          </div>
        )}
        <div className="overflow-y-auto flex-1 p-5">
          {children}
        </div>
      </div>
    </div>
  );
}
