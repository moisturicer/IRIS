import { useEffect, useState } from "react";

import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { describeFailure } from "@/features/publish/draft";

interface DeleteDraftDialogProps {
  recordId: number;
  title: string;
  open: boolean;
  onClose: () => void;
  /** The draft is gone on the server; drop its row. */
  onDeleted: (recordId: number) => void;
}

/**
 * Delete a draft the owner has not submitted. The server already allows it
 * (`DELETE /records/<id>/`, IR-508): a draft is removed at once, with no RDCO
 * decision, and its other owners are told (IR-517). Asked once, in a dialog
 * that keeps a failure in front of the owner rather than closing on it.
 *
 * Opened from the row's ⋯ menu (IR-1311, at the project owner's request:
 * row acts live in one menu, replacing IR-1279's trash can).
 */
export function DeleteDraftDialog({ recordId, title, open, onClose, onDeleted }: DeleteDraftDialogProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) setError(null);
  }, [open]);

  async function confirm() {
    setDeleting(true);
    setError(null);
    try {
      await recordsApi.delete(recordId);
      onClose();
      onDeleted(recordId);
    } catch (failure) {
      setError(describeFailure(failure, "Could not delete this draft. Try again.").message);
    } finally {
      setDeleting(false);
    }
  }

  return (
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
      onCancel={onClose}
    />
  );
}
