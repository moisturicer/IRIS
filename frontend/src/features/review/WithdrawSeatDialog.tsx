import { useState } from "react";

import { seatsApi } from "@/api/reviews";
import { Button, Modal } from "@/components/ui";
import { LOAD_ERROR } from "@/components/ui/fieldClasses";
import { errorDetail } from "@/lib/errorDetail";
import type { RemovalUnresolved } from "@/types/records";

import { RemovalWarning } from "./RemovalWarning";

interface WithdrawSeatDialogProps {
  seatId:       number;
  recordTitle:  string;
  officeLabel:  string;
  holderName:   string | null;
  /** What the holder leaves, from the console row (IR-1226). */
  unresolved:   RemovalUnresolved | null | undefined;
  /** Withdrawing finishes the office's review, on the reviews already done. */
  completesOffice: boolean;
  onClose:      () => void;
  onWithdrawn:  () => void;
}

/**
 * A coordinator takes a reviewer off a paper without naming anyone else
 * (ADR-032 §4, IR-1226). The office keeps the review: whoever else holds a
 * seat carries on, and when everyone left has finished, the office's review
 * is done on what they decided. The dialog says so before anyone commits.
 */
export function WithdrawSeatDialog({
  seatId, recordTitle, officeLabel, holderName, unresolved, completesOffice, onClose, onWithdrawn,
}: WithdrawSeatDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const who = holderName ?? "This reviewer";

  const submit = async () => {
    if (sending) return;
    setError(null);
    setSending(true);
    try {
      await seatsApi.withdraw(seatId);
      onWithdrawn();
    } catch (err) {
      setError(errorDetail(err, "The reviewer could not be withdrawn. Please try again."));
      setSending(false);
    }
  };

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Withdraw a reviewer"
      sheet
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="button" variant="danger" onClick={submit} loading={sending}>
            Withdraw
          </Button>
        </div>
      }
    >
      <div className="space-y-5">
        <p className="text-body text-stone-700">
          {who} stops reviewing <span className="font-semibold text-stone-900">{recordTitle}</span>. Nobody takes
          their place. To hand it to someone, use Reassign instead.
        </p>
        {completesOffice && (
          <p className="text-body font-semibold text-stone-900">
            This finishes {officeLabel}&apos;s review, using the reviews already done.
          </p>
        )}
        {unresolved && <RemovalWarning leaving={{ name: who, unresolved }} role="office" />}
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
