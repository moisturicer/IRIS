import { useId, useRef, type ReactNode } from "react";
import { DialogCloseX } from "@/components/ui/DialogCloseX";
import { useDialogFocus } from "@/hooks/useDialogFocus";

export interface EntryError {
  readonly title: string;
  /** Text, or text with a link: "resend verification email". */
  readonly body: ReactNode;
}

interface EntryErrorDialogProps {
  /** What went wrong, or `null` while nothing has. */
  readonly error: EntryError | null;
  readonly onClose: () => void;
  /**
   * Where focus goes when it closes, read once at open. Without it, focus
   * returns to whatever had it then, which after a submit is often nothing.
   */
  readonly returnTo?: HTMLElement | null;
}

/**
 * Why a sign-in or registration failed, said in front of the form (IR-1303).
 * It was an alert inside the form, which pushed every field down as it
 * appeared. The shell is the account-locked dialog's, so the entry screens
 * have one look for "this didn't work". It is an `alertdialog`: it interrupts,
 * and is answered only by closing it, with the X in its corner (IR-1327),
 * Escape or a click outside.
 */
export function EntryErrorDialog({ error, onClose, returnTo }: EntryErrorDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useDialogFocus(error !== null, panelRef, onClose, returnTo);

  if (!error) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" aria-hidden onClick={onClose} />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="relative max-h-screen overflow-y-auto bg-white rounded-dialog shadow-xl w-full max-w-sm px-8 py-8 text-center"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <DialogCloseX onClose={onClose} />

        {/* The error glyph AuthAlert used, at the lock dialog's size. */}
        <div
          className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-brand text-title font-bold text-white"
          aria-hidden
        >
          !
        </div>

        <h2 id={titleId} className="text-title font-bold text-stone-900">
          {error.title}
        </h2>
        <div id={descriptionId} className="mt-3 text-body text-stone-600 leading-relaxed">
          {error.body}
        </div>
      </div>
    </div>
  );
}
