import { useEffect, useId, useState, type FormEvent } from "react";

import { seatsApi } from "@/api/reviews";
import { Button, Modal, Skeleton } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/lib/errorDetail";
import type { AddReviewerOptions } from "@/types/records";

interface ReassignDialogProps {
  seatId:       number;
  assignmentId: number;
  recordTitle:  string;
  holderName:   string | null;
  onClose:      () => void;
  /** Reassigned: to whom. */
  onReassigned: (name: string) => void;
}

/**
 * A coordinator moves a seat to another member of their office, saying why
 * (ADR-032 §4, IR-623). The reason is required, and the Review timeline
 * shows it to everyone who reads the review, the reviewer who lost the seat
 * included.
 *
 * The member list is *Assign*'s (`GET /assignments/<id>/assign/`), offered
 * only to a coordinator of that office. Whoever already holds a seat is
 * listed but cannot be chosen.
 */
export function ReassignDialog({
  seatId, assignmentId, recordTitle, holderName, onClose, onReassigned,
}: ReassignDialogProps) {
  const ids = useId();
  const [options, setOptions] = useState<AddReviewerOptions | null>(null);
  const [loadFailed, setLoadFailed] = useState<string | null>(null);
  const [chosen, setChosen] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    seatsApi
      .assignOptions(assignmentId)
      .then(({ data }) => {
        if (!cancelled) setOptions(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadFailed(errorDetail(err, "Your office's members could not be loaded."));
      });
    return () => {
      cancelled = true;
    };
  }, [assignmentId]);

  const office = options?.party_label ?? "your office";
  const available = (options?.members ?? []).filter((m) => !m.seated);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!chosen || sending || options == null) return;
    if (!reason.trim()) {
      setError("Give a reason for the reassignment. The reviewers will see it on the Review timeline.");
      return;
    }
    setError(null);
    setSending(true);
    try {
      await seatsApi.reassign(seatId, Number(chosen), reason.trim());
      onReassigned(options.members.find((m) => String(m.id) === chosen)?.name ?? "your colleague");
    } catch (err) {
      setError(errorDetail(err, "The review could not be reassigned. Please try again."));
      setSending(false);
    }
  };

  const formId = `${ids}-form`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Reassign a reviewer"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!chosen} loading={sending}>
            Reassign
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-body text-stone-700">
          <span className="font-semibold text-stone-900">{recordTitle}</span>
          {holderName ? ` is with ${holderName}.` : "."} The person you choose takes it over and finds it in their
          To review. Its due date does not change.
        </p>

        {loadFailed ? (
          <p role="alert" className={LOAD_ERROR}>
            <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
            {loadFailed}
          </p>
        ) : options == null ? (
          <Skeleton rows={2} label="Loading your office's members…" />
        ) : (
          <div>
            <label htmlFor={`${ids}-member`} className={LABEL}>
              New reviewer at {office}
            </label>
            <select
              id={`${ids}-member`}
              value={chosen}
              onChange={(e) => setChosen(e.target.value)}
              className={fieldClasses(false)}
            >
              <option value="">{available.length ? "Choose a member" : "Everyone is already reviewing"}</option>
              {options.members.map((m) => (
                <option key={m.id} value={m.id} disabled={m.seated}>
                  {m.seated ? `${m.name} (already reviewing)` : m.name}
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label htmlFor={`${ids}-reason`} className={LABEL}>
            Reason <span className="font-normal text-brand">(required)</span>
          </label>
          <textarea
            id={`${ids}-reason`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            placeholder="For example: on leave until December."
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
