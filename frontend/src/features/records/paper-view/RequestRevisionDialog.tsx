import { useId, useRef, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/lib/errorDetail";
import { useAuthStore } from "@/store/auth.store";
import { useUIStore } from "@/store/ui.store";
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
  const userId = useAuthStore(s => s.user?.id);
  const [reason, setReason] = useState(() => readRevisionDraft(userId, record.id));
  const addToast = useUIStore((s) => s.addToast);
  const [sending, setSending] = useState(false);
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  const ready = reason.trim() !== "";

  const change = (value: string) => {
    setReason(value);
    writeRevisionDraft(userId, record.id, value);
  };

  /** Throw the unsent reason away, here and in the tab's session. */
  const discard = () => {
    setReason("");
    clearRevisionDraft(userId, record.id);
    addToast({ type: "info", message: "Draft discarded." });
    reasonRef.current?.focus();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setSending(true);
    try {
      await recordsApi.requestRevision(record.id, { reason: reason.trim() });
      clearRevisionDraft(userId, record.id);
      onDone("Revision requested. The owner has been notified.");
    } catch (err) {
      // A toast, not a line in the dialog: the form keeps its size, and the
      // reason stays in the box.
      addToast({
        type: "error",
        persist: true,
        message:
          `${errorDetail(err, "Your request could not be sent. Please try again.")} ` +
          "Your reason is kept.",
      });
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
        <div className="flex items-center justify-between gap-2">
          {reason !== "" ? (
            <Button type="button" variant="ghost" onClick={discard} disabled={sending}>
              <i className="fas fa-trash-can text-label" aria-hidden />
              Discard draft
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
              Cancel
            </Button>
            <Button type="submit" form={formId} disabled={!ready} loading={sending}>
              Request Revision
            </Button>
          </div>
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
            ref={reasonRef}
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
      </form>
    </Modal>
  );
}
