import { useId, useRef, type ReactNode } from "react";
import { useDialogFocus } from "@/hooks/useDialogFocus";
import { cn } from "@/lib/utils";

interface ChatDrawerProps {
  /** The drawer's name, its heading and its accessible name. */
  title:       string;
  /** One line under the heading saying what the drawer holds. */
  description?: string;
  /** Which edge it comes from: history on the start side, sources on the end. */
  side:        "start" | "end";
  /** The close control's accessible name. */
  closeLabel:  string;
  onClose:     () => void;
  /** The control that opened it, recorded on activation: focus goes back there. */
  returnTo:    HTMLElement | null;
  children:    ReactNode;
}

/**
 * History or sources over the answer when the page is too narrow to hold
 * them beside it (IR-570). A dialog, because the answer behind it waits: the
 * page marks the rest inert, focus moves in, Tab stays inside, Escape or the
 * scrim closes it, and focus returns to the button that opened it.
 *
 * Drawn as the Paper view's drawer is (IR-569): the `overlay` role, one soft
 * shadow towards the answer and a `stone-900/25` scrim, no card around it.
 * Mounted only while open, so its entrance is the one `panel-in` motion,
 * from the edge it belongs to.
 */
export function ChatDrawer({ title, description, side, closeLabel, onClose, returnTo, children }: ChatDrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const headingId = useId();
  useDialogFocus(true, panelRef, onClose, returnTo);

  return (
    <div className="absolute inset-0 z-40 flex">
      <div aria-hidden onClick={onClose} className="absolute inset-0 bg-stone-900/25" />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        className={cn(
          "relative flex flex-col h-full w-[min(88%,320px)] bg-overlay focus:outline-none",
          side === "start"
            ? "mr-auto motion-safe:animate-panel-in-start shadow-[12px_0_32px_rgb(41_37_36/0.12)]"
            : "ml-auto motion-safe:animate-panel-in shadow-[-12px_0_32px_rgb(41_37_36/0.12)]",
        )}
      >
        <div className="shrink-0 flex items-start gap-2 pl-4 pr-1.5 py-1.5 min-h-[56px] border-b border-stone-200">
          <div className="min-w-0 flex-1 py-2">
            <h2 id={headingId} className="text-heading font-semibold text-stone-900">{title}</h2>
            {description && <p className="text-2xs text-stone-500 mt-0.5">{description}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={closeLabel}
            className="shrink-0 w-11 h-11 rounded-lg flex items-center justify-center text-stone-500
              hover:bg-stone-100 hover:text-stone-800 transition-colors"
          >
            <i className="fas fa-xmark text-base" aria-hidden />
          </button>
        </div>
        <div className="flex-1 min-h-0 flex flex-col">{children}</div>
      </div>
    </div>
  );
}
