import { useEffect, useId, useState, type FormEvent } from "react";

import { seatsApi } from "@/api/reviews";
import { Button, Modal, Skeleton } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/features/document-requests/errorDetail";
import type { AddReviewerOptions } from "@/types/records";

interface AddReviewerDialogProps {
  assignmentId: number;
  onClose: () => void;
  /** Added: the colleague's name and the office, for the bar to announce. */
  onAdded: (name: string, officeLabel: string) => void;
}

/**
 * Bring a colleague from your own office into this review (ADR-032 §4,
 * IR-269).
 *
 * Only your own office: involving another office is routing, a different act
 * with its own button, and the server refuses anyone else here. The members
 * come from the server, which offers the list only to a seat holder. Someone
 * already reviewing is listed but cannot be chosen, so the list still shows
 * who is on it.
 */
export function AddReviewerDialog({ assignmentId, onClose, onAdded }: AddReviewerDialogProps) {
  const ids = useId();
  const [options, setOptions] = useState<AddReviewerOptions | null>(null);
  const [loadFailed, setLoadFailed] = useState<string | null>(null);
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    seatsApi
      .addReviewerOptions(assignmentId)
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
    setError(null);
    setSending(true);
    try {
      await seatsApi.addReviewer(assignmentId, Number(chosen));
      const name = options.members.find((m) => String(m.id) === chosen)?.name ?? "Your colleague";
      onAdded(name, options.party_label);
    } catch (err) {
      setError(errorDetail(err, "The reviewer could not be added. Please try again."));
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const pickId = `${ids}-member`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Add a reviewer"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} disabled={!chosen} loading={sending}>
            Add reviewer
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-5">
        <p className="text-[14px] text-stone-700 leading-relaxed">
          They review this record for {office} alongside you. {office} finishes once everyone reviewing
          for it has. To involve another office, route the record instead.
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
            <label htmlFor={pickId} className={LABEL}>
              Reviewer at {office}
            </label>
            <select
              id={pickId}
              value={chosen}
              onChange={(e) => setChosen(e.target.value)}
              className={fieldClasses(false)}
            >
              <option value="">{available.length ? "Choose a colleague" : "Everyone is already reviewing"}</option>
              {options.members.map((m) => (
                <option key={m.id} value={m.id} disabled={m.seated}>
                  {m.seated ? `${m.name} (already reviewing)` : m.name}
                </option>
              ))}
            </select>
          </div>
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
