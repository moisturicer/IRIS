import { useEffect, useState } from "react";

import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { describeFailure } from "@/features/publish/draft";
import type { MyResearchItem } from "@/types/records";

/**
 * Which of the owner's deletes a row offers. Both are the same request,
 * `DELETE /records/<id>/` (IR-508), which acts by the record's status:
 * - `draft`: a draft the owner has not submitted is removed at once.
 * - `withdraw`: a paper in review is removed at once and its review ends;
 *   the Adviser and every office reviewing it are told (`withdraw_submission`,
 *   IR-1282).
 */
export type DeleteKind = "draft" | "withdraw";

export const DELETE_WORDS: Record<DeleteKind, { action: string; title: string; message: (title: string) => string; failed: string }> = {
  draft: {
    action: "Delete draft",
    title: "Delete this draft?",
    message: (title) => `“${title}” and its files will be removed. It can't be restored.`,
    failed: "Could not delete this draft. Try again.",
  },
  withdraw: {
    action: "Withdraw and delete",
    title: "Withdraw and delete this paper?",
    message: (title) =>
      `“${title}” leaves review and is removed with its files. Your Adviser and any office reviewing it stop, and are told. It can't be restored.`,
    failed: "Could not withdraw this paper. Try again.",
  },
};

/**
 * Which delete a row offers, if any: a draft's, or withdrawing a paper in
 * review, which the server names `withdraw_submission` (IR-1282). Accepted
 * work (`request_deletion`, a request RDCO decides) and rejected records get
 * none here.
 */
export function deleteKindOf(item: MyResearchItem): DeleteKind | null {
  if (item.pipeline_status === "draft") return "draft";
  if (item.delete_act === "withdraw_submission") return "withdraw";
  return null;
}

interface DeleteRecordDialogProps {
  kind: DeleteKind;
  recordId: number;
  title: string;
  open: boolean;
  onClose: () => void;
  /** The record is gone on the server; drop its row. */
  onDeleted: (recordId: number) => void;
}

/**
 * The one question before a draft is deleted or a paper in review is
 * withdrawn, kept open with its failure rather than closing on it. Opened
 * from the row's ⋯ menu (IR-1311, at the project owner's request: row acts
 * live in one menu, replacing IR-1279's and IR-1282's trash can). Publish asks
 * the draft's question the same way.
 */
export function DeleteRecordDialog({ kind, recordId, title, open, onClose, onDeleted }: DeleteRecordDialogProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const words = DELETE_WORDS[kind];

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
      setError(describeFailure(failure, words.failed).message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <ConfirmDialog
      open={open}
      title={words.title}
      message={words.message(title)}
      confirmLabel={words.action}
      danger
      focusCancel
      confirming={deleting}
      error={error}
      onConfirm={() => void confirm()}
      onCancel={onClose}
    />
  );
}
