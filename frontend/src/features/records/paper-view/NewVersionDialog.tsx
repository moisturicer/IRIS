import { useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { errorDetail } from "@/lib/errorDetail";
import { joinLabels } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import type { NewVersionHint, ResponseLetterEntry } from "@/types/records";

import { LetterEntries } from "./threads/ResponseLetter";

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
 *
 * **The response to reviewers** (ADR-032 §7, IR-876): the dialog shows the
 * letter the Version will carry, assembled from the owner's answers as they
 * stand, and holds *Submit* while the server says a *Must fix* has none.
 */
export function NewVersionDialog({ recordId, hint, newManuscript, onClose, onDone }: NewVersionDialogProps) {
  const addToast = useUIStore((s) => s.addToast);
  const [sending, setSending] = useState(false);
  const blockedId = useId();
  const letter = hint.letter ?? [];

  const submit = async () => {
    if (sending) return;
    setSending(true);
    try {
      await recordsApi.submitNewVersion(recordId);
      onDone(`v${hint.number} submitted. The reviewers who asked for changes have been notified.`);
    } catch (err) {
      // A toast, not a line in the dialog, so the confirmation keeps its size.
      addToast({
        type: "error",
        persist: true,
        message: errorDetail(err, "The new version could not be submitted. Please try again."),
      });
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
          <Button
            type="button"
            onClick={() => void submit()}
            loading={sending}
            disabled={hint.blocked != null}
            aria-describedby={hint.blocked ? blockedId : undefined}
          >
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
        {letter.length > 0 && <LetterPreview entries={letter} />}
        {hint.blocked && (
          <p id={blockedId} className="text-[14px] text-brand leading-relaxed">{hint.blocked}</p>
        )}
      </div>
    </Modal>
  );
}

function LetterPreview({ entries }: { entries: ResponseLetterEntry[] }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <h3 id={headingId} className="text-[14px] font-semibold text-stone-900">Response to reviewers</h3>
      <p className="text-small text-stone-600">
        Sent with this version, from your answers in Threads. Reviewers read it first.
      </p>
      <LetterEntries entries={entries} />
    </section>
  );
}
