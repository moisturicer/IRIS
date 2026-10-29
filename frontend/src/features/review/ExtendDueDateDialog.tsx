import { useId, useState, type FormEvent } from "react";

import { seatsApi } from "@/api/reviews";
import { Button, Modal } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/features/document-requests/errorDetail";
import { formatDate } from "@/lib/utils";

interface ExtendDueDateDialogProps {
  assignmentId: number;
  recordTitle:  string;
  /** The current due date, as the server sent it. */
  dueAt:        string;
  onClose:      () => void;
  onExtended:   () => void;
}

/** The calendar day `iso` falls on in Manila, as `YYYY-MM-DD`. */
function manilaDay(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Manila" }).format(new Date(iso));
}

/** The day after `day` (`YYYY-MM-DD`), counted on the calendar alone. */
function nextDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
}

/**
 * A coordinator moves an assignment's due date later, saying why (ADR-043 §6,
 * IR-623). A due date is always the end of a Manila working day, so the
 * coordinator picks a day and the time is fixed at 23:59 +08:00. The server
 * refuses anything not later than the current date.
 */
export function ExtendDueDateDialog({
  assignmentId, recordTitle, dueAt, onClose, onExtended,
}: ExtendDueDateDialogProps) {
  const ids = useId();
  const [day, setDay] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (sending) return;
    if (!day) {
      setError("Pick the new due date.");
      return;
    }
    if (!reason.trim()) {
      setError("Give a reason for the extension. It is shown on the Review timeline.");
      return;
    }
    setError(null);
    setSending(true);
    try {
      await seatsApi.extend(assignmentId, `${day}T23:59:00+08:00`, reason.trim());
      onExtended();
    } catch (err) {
      setError(errorDetail(err, "The due date could not be extended. Please try again."));
      setSending(false);
    }
  };

  const formId = `${ids}-form`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Extend the due date"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} loading={sending}>
            Extend
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-body text-stone-700">
          <span className="font-semibold text-stone-900">{recordTitle}</span> is due {formatDate(dueAt)}.
          The new date ends at 23:59, Manila time.
        </p>

        <div>
          <label htmlFor={`${ids}-day`} className={LABEL}>
            New due date
          </label>
          <input
            id={`${ids}-day`}
            type="date"
            value={day}
            min={nextDay(manilaDay(dueAt))}
            onChange={(e) => setDay(e.target.value)}
            className={fieldClasses(false)}
          />
        </div>

        <div>
          <label htmlFor={`${ids}-reason`} className={LABEL}>
            Reason <span className="font-normal text-brand">(required)</span>
          </label>
          <textarea
            id={`${ids}-reason`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="For example: the committee meets on Monday."
            className={fieldClasses(false)}
          />
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
