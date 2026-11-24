import { useState } from "react";

import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Tooltip } from "@/components/ui/Tooltip";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { describeFailure } from "@/features/publish/draft";
import { cn } from "@/lib/utils";

/**
 * Which of the owner's deletes the trash can does. Both are the same request,
 * `DELETE /records/<id>/` (IR-508), which acts by the record's status:
 * - `draft`: a draft the owner has not submitted is removed at once.
 * - `withdraw`: a paper in review is removed at once and its review ends;
 *   the Adviser and every office reviewing it are told (`withdraw_submission`,
 *   IR-1282).
 */
export type DeleteKind = "draft" | "withdraw";

const WORDS: Record<DeleteKind, { action: string; title: string; message: (title: string) => string; failed: string }> = {
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

interface DeleteRecordProps {
  kind: DeleteKind;
  recordId: number;
  title: string;
  /** The record is gone on the server; drop its row. */
  onDeleted: (recordId: number) => void;
}

/**
 * A red trash can, rightmost under a My Library row's *Updated* date, named
 * for its paper, with the act as its tooltip (IR-1256; brought back from
 * IR-1261's "⋯" menu by IR-1279; offered on a paper in review by IR-1282).
 * The row itself opens the paper. Asked once, in a dialog that keeps a
 * failure in front of the owner rather than closing on it. Publish asks the
 * draft's question the same way.
 */
export function DeleteRecord({ kind, recordId, title, onDeleted }: DeleteRecordProps) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const words = WORDS[kind];

  async function confirm() {
    setDeleting(true);
    setError(null);
    try {
      await recordsApi.delete(recordId);
      setOpen(false);
      onDeleted(recordId);
    } catch (failure) {
      setError(describeFailure(failure, words.failed).message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <Tooltip label={words.action}>
        <button
          type="button"
          aria-label={`${words.action} “${title}”`}
          // No fill or outline at rest (IR-1084): a quiet icon beside the row's text.
          className={cn(
            "inline-flex h-9 w-9 items-center justify-center rounded-full text-brand",
            "hover:bg-stone-100 hover:text-brand-dark",
            COLOUR_TRANSITION,
            FOCUS_RING,
          )}
          onClick={() => { setError(null); setOpen(true); }}
        >
          <i className="fas fa-trash-can" aria-hidden />
        </button>
      </Tooltip>
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
        onCancel={() => setOpen(false)}
      />
    </>
  );
}
