import { useState } from "react";

import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { describeFailure } from "@/features/publish/draft";
import { cn } from "@/lib/utils";

interface DeleteDraftProps {
  recordId: number;
  title: string;
  /** The draft is gone on the server; drop its row. */
  onDeleted: (recordId: number) => void;
}

/**
 * Delete a draft the owner has not submitted. The server already allows it
 * (`DELETE /records/<id>/`, IR-508): a draft is removed at once, with no RDCO
 * decision, and its other owners are told (IR-517). Asked once, in a dialog
 * that keeps a failure in front of the owner rather than closing on it.
 */
export function DeleteDraft({ recordId, title, onDeleted }: DeleteDraftProps) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setDeleting(true);
    setError(null);
    try {
      await recordsApi.delete(recordId);
      setOpen(false);
      onDeleted(recordId);
    } catch (failure) {
      setError(describeFailure(failure, "Could not delete this draft. Try again.").message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <button
        type="button"
        // A ghost (IR-1084): quieter than Continue draft, with no fill or outline at rest.
        className={cn(
          "inline-flex min-h-9 items-center justify-center gap-2 rounded-full px-4 text-small font-semibold text-stone-700",
          "hover:bg-stone-100 hover:text-brand",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
        onClick={() => { setError(null); setOpen(true); }}
      >
        <i className="fas fa-trash-can text-label" aria-hidden />
        Delete <span className="sr-only">draft “{title}”</span>
      </button>
      <ConfirmDialog
        open={open}
        title="Delete this draft?"
        message={`“${title}” and its files will be removed. It can't be restored.`}
        confirmLabel="Delete draft"
        danger
        focusCancel
        confirming={deleting}
        error={error}
        onConfirm={() => void confirm()}
        onCancel={() => setOpen(false)}
      />
    </>
  );
}
