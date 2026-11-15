import { useId, useRef, type ReactNode } from "react";
import { useDialogFocus } from "@/hooks/useDialogFocus";

/**
 * The dialog widths (IR-1043; 01-design-system.md "Dialog sizes"). A name, not a
 * width class, so an unknown size fails type-checking and every dialog is one
 * of four. `sm` asks a question, `md` is the default form, `lg` is a task with
 * room for two columns of fields, `xl` is Publish's two-pane step only.
 * A sheet is full width below `md`, so its width starts there. Both strings
 * are written out whole so Tailwind finds them.
 */
const SIZE_CLASS = {
  sm: { dialog: "max-w-dialog-sm", sheet: "md:max-w-dialog-sm" },
  md: { dialog: "max-w-dialog-md", sheet: "md:max-w-dialog-md" },
  lg: { dialog: "max-w-dialog-lg", sheet: "md:max-w-dialog-lg" },
  xl: { dialog: "max-w-dialog-xl", sheet: "md:max-w-dialog-xl" },
} as const;

export type ModalSize = keyof typeof SIZE_CLASS;

interface ModalProps {
  open:     boolean;
  onClose:  () => void;
  title?:   string;
  children: ReactNode;
  /** A named width: "sm", "md", "lg" or "xl". Defaults to "md". */
  size?:    ModalSize;
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
  size = "md",
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
            ? `relative bg-overlay shadow-xl w-full h-full md:h-auto md:rounded-dialog ${SIZE_CLASS[size].sheet} md:max-h-[90vh] flex flex-col outline-none`
            : `relative bg-overlay rounded-dialog shadow-xl w-full ${SIZE_CLASS[size].dialog} max-h-[90vh] flex flex-col outline-none`
        }
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
      >
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-stone-200">
            <h2
              id={titleId}
              className={displayTitle ? "font-display text-title text-stone-900" : "text-heading font-semibold text-stone-900"}
            >
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex min-h-11 min-w-11 items-center justify-center p-1 rounded-control text-stone-500 hover:text-stone-700 hover:bg-stone-100"
              aria-label="Close"
            >
              <i className="fa fa-times text-body" aria-hidden />
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
