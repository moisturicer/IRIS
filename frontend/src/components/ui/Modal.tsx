import { useId, useRef, type ReactNode } from "react";
import { useDialogFocus } from "@/hooks/useDialogFocus";

interface ModalProps {
  open:     boolean;
  onClose:  () => void;
  title?:   string;
  children: ReactNode;
  /** px width class, e.g. "max-w-lg". Defaults to "max-w-lg". */
  size?:    string;
  /**
   * Full screen below `md`, a centred dialog above it (spec §4.13). For a
   * dialog that is a task rather than a question, such as Publish.
   */
  sheet?:   boolean;
  /** Pinned under the scrolling body, so the step's actions never scroll away. */
  footer?:  ReactNode;
  /** The title in the display face, as a content title (01-design-system §0). */
  displayTitle?: boolean;
}

export function Modal({
  open,
  onClose,
  title,
  children,
  size = "max-w-lg",
  sheet = false,
  footer,
  displayTitle = false,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  // `useId` rather than a literal "modal-title": two dialogs mounted at once
  // (a confirm on top of a form) would otherwise share one id, and
  // `aria-labelledby` would resolve to whichever rendered first.
  const titleId = useId();

  // Escape, focus in, Tab kept inside, focus restored on close (IR-158).
  useDialogFocus(open, panelRef, onClose);

  if (!open) return null;

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center ${sheet ? "md:p-4" : "p-4"}`}>
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
        className={
          sheet
            ? `relative bg-overlay shadow-xl w-full h-full md:h-auto md:rounded-xl ${size} md:max-h-[90vh] flex flex-col outline-none`
            : `relative bg-overlay rounded-xl shadow-xl w-full ${size} max-h-[90vh] flex flex-col outline-none`
        }
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
      >
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-stone-200">
            <h2
              id={titleId}
              className={displayTitle ? "font-display text-title text-stone-900" : "text-[16px] font-semibold text-stone-900"}
            >
              {title}
            </h2>
            <button
              onClick={onClose}
              className="p-1 rounded-md text-stone-500 hover:text-stone-700 hover:bg-stone-100"
              aria-label="Close"
            >
              <i className="fa fa-times text-[15px]" aria-hidden />
            </button>
          </div>
        )}
        <div className="overflow-y-auto flex-1 p-5">
          {children}
        </div>
        {footer && <div className="border-t border-stone-200 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}
