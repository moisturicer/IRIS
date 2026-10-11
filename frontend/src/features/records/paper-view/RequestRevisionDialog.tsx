import { useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/features/document-requests/errorDetail";
import type { RecordDetail } from "@/types/records";

import { clearRevisionDraft, readRevisionDraft, writeRevisionDraft } from "./revisionDraft";

interface RequestRevisionDialogProps {
  record: RecordDetail;
  onClose: () => void;
  /** Asked: the sentence the bar announces. */
  onDone: (outcome: string) => void;
}

/**
 * *Request Revision* for the party the viewer reviews for (ADR-032 §5, IR-272).
 *
 * The copy is the retired review form's, kept verbatim (ui-ux/16 §4). The reviewer's
 * own review stays open for the next version, and nothing can be decided
 * until the owner submits one -- the server decides both, so this dialog
 * only says so. A reason is required: the owner acts on it.
 *
 * **The typed reason survives** (IR-143's carried criteria), as in
 * `OfficeReviewDialog`: kept in the tab's session as it is typed, and left in
 * the box beside the server's reason when the request is refused because the
 * record moved while the dialog was open. Nothing is retried.
 */
export function RequestRevisionDialog({ record, onClose, onDone }: RequestRevisionDialogProps) {
  const ids = useId();
  const party = record.revision.label ?? "your review";
  // The version the request is made against: the latest one. Null when the
  // record has none recorded, and then nothing is claimed.
  const version = record.versions?.length ? record.versions[record.versions.length - 1].number : null;
  const [reason, setReason] = useState(() => readRevisionDraft(record.id));
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const ready = reason.trim() !== "";

  const change = (value: string) => {
    setReason(value);
    writeRevisionDraft(record.id, value);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await recordsApi.requestRevision(record.id, { reason: reason.trim() });
      clearRevisionDraft(record.id);
      onDone("Revision requested. The owner has been notified.");
    } catch (err) {
      setError(
        `${errorDetail(err, "Your request could not be sent. Please try again.")} ` +
          "Your reason is kept.",
      );
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const reasonId = `${ids}-reason`;
  const helpId = `${reasonId}-help`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Request Revision"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!ready} loading={sending}>
            Request Revision
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-[14px] text-stone-700 leading-relaxed">
          Send back to the owner for changes. They may resubmit after revising.{" "}
          Nothing can be decided until they do, and your review for {party} stays open for the new
          version.
        </p>

        <div>
          <label htmlFor={reasonId} className={LABEL}>
            What needs revising?
          </label>
          <textarea
            id={reasonId}
            required
            rows={5}
            value={reason}
            onChange={(e) => change(e.target.value)}
            aria-describedby={helpId}
            className={fieldClasses(false)}
          />
          <p id={helpId} className="mt-1 text-[13px] text-stone-600">
            The owner sees this as you write it
            {version != null ? `, against v${version}, the version you reviewed` : ""}.
          </p>
        </div>

        {error && (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
