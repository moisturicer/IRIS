import { useEffect, useId, useState, type FormEvent } from "react";

import { seatsApi } from "@/api/reviews";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { Button, Modal, Select, Skeleton } from "@/components/ui";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/lib/errorDetail";
import { failureMessage } from "@/lib/readFailure";
import type { AddReviewerOptions } from "@/types/records";

interface AssignReviewerDialogProps {
  assignmentId: number;
  recordTitle:  string;
  onClose:      () => void;
  /** Assigned: who, and whether it was the coordinator themselves. */
  onAssigned:   (name: string, self: boolean) => void;
  viewerId:     number | null;
}

/**
 * A coordinator seats a member of their own office on an unclaimed record
 * (ADR-032 §4, IR-268).
 *
 * The list is the server's (`GET /assignments/<id>/assign/`), offered only to
 * a coordinator of that office. Someone already reviewing is listed but cannot
 * be chosen, so the list still shows who is on it.
 */
export function AssignReviewerDialog({
  assignmentId, recordTitle, onClose, onAssigned, viewerId,
}: AssignReviewerDialogProps) {
  const ids = useId();
  const [options, setOptions] = useState<AddReviewerOptions | null>(null);
  const [loadFailed, setLoadFailed] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoadFailed(null);
    seatsApi
      .assignOptions(assignmentId)
      .then(({ data }) => {
        if (!cancelled) setOptions(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadFailed(failureMessage(err, { lead: "Your office's members could not be loaded." }));
      });
    return () => {
      cancelled = true;
    };
  }, [assignmentId, attempt]);

  const office = options?.party_label ?? "your office";
  const available = (options?.members ?? []).filter((m) => !m.seated);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!chosen || sending || options == null) return;
    setError(null);
    setSending(true);
    try {
      await seatsApi.assign(assignmentId, Number(chosen));
      const name = options.members.find((m) => String(m.id) === chosen)?.name ?? "your colleague";
      onAssigned(name, Number(chosen) === viewerId);
    } catch (err) {
      setError(errorDetail(err, "The reviewer could not be assigned. Please try again."));
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const pickId = `${ids}-member`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Assign a reviewer"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!chosen} loading={sending}>
            Assign
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-[14px] text-stone-700 leading-relaxed">
          <span className="font-semibold text-stone-900">{recordTitle}</span> is waiting in {office}'s
          pool. The person you choose reviews it for {office} and finds it in their To review.
        </p>

        {loadFailed ? (
          <LoadFailedAlert message={loadFailed} onRetry={() => setAttempt((n) => n + 1)} />
        ) : options == null ? (
          <Skeleton rows={2} label="Loading your office's members…" onRetry={() => setAttempt((n) => n + 1)} />
        ) : (
          <Select id={pickId} label={`Reviewer at ${office}`} required value={chosen} onChange={(e) => setChosen(e.target.value)}>
            <option value="">{available.length ? "Choose a member" : "Everyone is already reviewing"}</option>
            {options.members.map((m) => (
              <option key={m.id} value={m.id} disabled={m.seated}>
                {m.seated ? `${m.name} (already reviewing)` : m.name}
              </option>
            ))}
          </Select>
        )}

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
