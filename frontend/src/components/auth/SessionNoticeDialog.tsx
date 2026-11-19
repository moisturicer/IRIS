import { useId, useRef } from "react";
import { Button } from "@/components/ui/Button";
import { useDialogFocus } from "@/hooks/useDialogFocus";

interface SessionNoticeDialogProps {
  /** Why this person was signed out; nothing is shown while null. */
  notice: { title: string; text: string } | null;
  onClose: () => void;
}

/**
 * Why a person was signed out, in front of the sign-in page (IR-1197): a
 * session that ended (IR-645, IR-1081) or a password changed in Settings
 * (IR-642). It is a dialog, not a banner in the form, because it reports
 * something that happened while they were away, not a problem with what they
 * just typed. One button closes it, as do Escape and a click outside.
 */
export function SessionNoticeDialog({ notice, onClose }: SessionNoticeDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useDialogFocus(notice !== null, panelRef, onClose);

  if (!notice) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" aria-hidden onClick={onClose} />
      <div
        ref={panelRef}
        tabIndex={-1}
        className="relative max-h-screen overflow-y-auto bg-white rounded-dialog shadow-xl w-full max-w-sm px-8 py-8 text-center outline-none"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <div className="mx-auto w-14 h-14 rounded-full bg-stone-100 flex items-center justify-center mb-5">
          <i className="fas fa-clock-rotate-left text-heading text-brand" aria-hidden />
        </div>

        <h2 id={titleId} className="text-title font-bold text-stone-900">
          {notice.title}
        </h2>
        <p id={descriptionId} className="mt-3 text-body text-stone-600 leading-relaxed">
          {notice.text}
        </p>

        <Button type="button" variant="primary" size="full" onClick={onClose} className="mt-8">
          Sign in again
        </Button>
      </div>
    </div>
  );
}
