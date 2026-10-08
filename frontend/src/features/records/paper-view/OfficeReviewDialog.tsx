import { useId, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Button, Modal } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/features/document-requests/errorDetail";
import type { OfficeReviewOutcome, RecordDetail } from "@/types/records";

import {
  clearOfficeReviewDrafts,
  readOfficeReviewDraft,
  writeOfficeReviewDraft,
} from "./officeReviewDraft";

interface OfficeReviewDialogProps {
  record: RecordDetail;
  outcome: OfficeReviewOutcome;
  onClose: () => void;
  /** Recorded: the sentence the bar announces. */
  onDone: (outcome: string) => void;
}

/**
 * *Clear* or *Record finding* for the office the viewer is seated for
 * (ADR-032 §3-§4, IR-269).
 *
 * Either ends the viewer's own part of the office's review. The office
 * finishes when every reviewer seated for it has, and the record goes to
 * RDCO once no office is still reviewing -- the server decides both, so this
 * dialog only says so. A finding needs a comment; a clearance may carry one.
 * Offices never reject and never publish, so neither is offered.
 *
 * **The typed comment survives** (IR-143's carried criteria): it is kept in
 * the tab's session as it is typed, so closing the dialog to read the paper
 * loses nothing, and a refusal -- the record moved while the dialog was open
 * -- leaves it in the box beside the server's reason. Nothing is retried: the
 * server refuses a verdict into a changed state, and the reviewer decides
 * again on what is there now.
 */
export function OfficeReviewDialog({ record, outcome, onClose, onDone }: OfficeReviewDialogProps) {
  const ids = useId();
  const office = record.office_review.label ?? "your office";
  const finding = outcome === "finding";
  const [comment, setComment] = useState(() => readOfficeReviewDraft(record.id, outcome));
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const ready = !finding || comment.trim() !== "";

  const change = (value: string) => {
    setComment(value);
    writeOfficeReviewDraft(record.id, outcome, value);
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await recordsApi.officeReview(record.id, { outcome, comment: comment.trim() });
      clearOfficeReviewDrafts(record.id);
      onDone(finding ? `Finding recorded for ${office}.` : `Cleared for ${office}.`);
    } catch (err) {
      setError(
        `${errorDetail(err, "Your review could not be recorded. Please try again.")} ` +
          "Your comment is kept.",
      );
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const commentId = `${ids}-comment`;
  const helpId = `${commentId}-help`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title={finding ? `Record a finding for ${office}` : `Clear for ${office}`}
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!ready} loading={sending}>
            {finding ? "Record finding" : "Clear"}
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-[14px] text-stone-700 leading-relaxed">
          {finding
            ? `A finding records a concern for ${office}. It does not reject the record or send it back: RDCO sees it and decides.`
            : `You find nothing for ${office} to hold this record on.`}{" "}
          Your part of {office}&apos;s review ends here. {office} finishes once everyone reviewing for it
          has.
        </p>

        <div>
          <label htmlFor={commentId} className={LABEL}>
            {finding ? "What is the finding?" : "Comment (optional)"}
          </label>
          <textarea
            id={commentId}
            required={finding}
            rows={4}
            value={comment}
            onChange={(e) => change(e.target.value)}
            aria-describedby={helpId}
            className={fieldClasses(false)}
          />
          <p id={helpId} className="mt-1 text-[13px] text-stone-600">
            {finding
              ? "RDCO and the author see this with the record."
              : "If you add one, the author and the other reviewers see it with the record."}
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
