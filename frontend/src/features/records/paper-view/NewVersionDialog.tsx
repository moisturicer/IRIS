import { useState } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/features/document-requests/errorDetail";
import { joinLabels } from "@/lib/utils";
import type { NewVersionHint } from "@/types/records";

interface NewVersionDialogProps {
  recordId: number;
  hint: NewVersionHint;
  /** The owner's revised manuscript goes with this version. */
  newManuscript: boolean;
  onClose: () => void;
  /** Submitted: the sentence the page announces. */
  onDone: (outcome: string) => void;
}

/**
 * What submitting does, in the words the confirmation uses (IR-273):
 * "IERC will review v3. ITSO's clearance is kept." Both halves come from
 * the server's `revision.new_version`, which applies the resubmission policy,
 * so nothing here decides who reviews again.
 */
export function newVersionSummary(hint: NewVersionHint): string {
  const review = `${joinLabels(hint.rereview)} will review v${hint.number}.`;
  if (hint.kept.length === 0) return review;
  const kept =
    hint.kept.length === 1
      ? `${hint.kept[0]}'s clearance is kept.`
      : `${joinLabels(hint.kept)} keep their clearances.`;
  return `${review} ${kept}`;
}

/**
 * *Submit new version* (ADR-032 §5, IR-273): the owner answers every open
 * revision request at once. The confirmation names who reviews it and whose
 * clearance survives, since that is what ADR-003's clearance-aware
 * resubmission promises the owner. The server re-checks that something
 * changed; its refusal is shown as it words it.
 */
export function NewVersionDialog({ recordId, hint, newManuscript, onClose, onDone }: NewVersionDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const submit = async () => {
    if (sending) return;
    setError(null);
    setSending(true);
    try {
      await recordsApi.submitNewVersion(recordId);
      onDone(`v${hint.number} submitted. The reviewers who asked for changes have been notified.`);
    } catch (err) {
      setError(errorDetail(err, "The new version could not be submitted. Please try again."));
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Submit new version"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void submit()} loading={sending}>
            Submit v{hint.number}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <p className="text-[14px] text-stone-900 font-semibold leading-relaxed">{newVersionSummary(hint)}</p>
        <p className="text-[14px] text-stone-700 leading-relaxed">
          {newManuscript
            ? "Your revised manuscript and any details you edited go with it."
            : "Your manuscript is unchanged; the details you edited and the documents you uploaded go with it."}{" "}
          Every earlier version stays in the record&rsquo;s history.
        </p>
        {error && (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
