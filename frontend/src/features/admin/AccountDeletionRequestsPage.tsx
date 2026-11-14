/**
 * The System Admin's Account Deletion Requests page (ADR-051 §8-§9, IR-788).
 *
 * Lists pending requests with who asked and when, and what still blocks each
 * one in plain words. Confirm stays disabled while anything blocks it, and
 * says RDCO or the person must clear it. Reject needs a reason, which the
 * person receives. Confirm asks first and says it can't be undone.
 *
 * Every control comes from the request's `capabilities`, so the screen
 * compares no role names. A decision the server refuses (someone else got
 * there first, or a blocker appeared) shows the server's own reason.
 *
 *   GET  /users/deletion-requests/
 *   POST /users/deletion-requests/<id>/confirm/
 *   POST /users/deletion-requests/<id>/reject/   {reason}
 */
import { useId, useState, type FormEvent } from "react";
import { accountsApi, type AccountDeletionRequest } from "@/api/accounts";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { LABEL, LOAD_ERROR, WARNING_NOTICE, fieldClasses } from "@/components/ui/fieldClasses";
import { Spinner } from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { failureMessage } from "@/lib/readFailure";
import { useApiRead } from "@/hooks/useApiRead";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { formatDate } from "@/lib/utils";

const FAILED = "That did not go through. Please try again.";

function RejectDialog({
  request, onClose, onDone,
}: { request: AccountDeletionRequest; onClose: () => void; onDone: () => void }) {
  const ids = useId();
  const [reason, setReason] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = reason.trim() !== "";
  const formId = `${ids}-form`;
  const reasonId = `${ids}-reason`;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await accountsApi.rejectDeletion(request.id, reason.trim());
      onDone();
    } catch (err) {
      // The reason stays in the box beside the server's refusal.
      setError(fieldError(err, "reason") ?? errorDetail(err, FAILED));
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title="Reject account deletion"
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} variant="danger" disabled={!ready} loading={sending}>
            Reject request
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <p className="text-[14px] text-stone-700 leading-relaxed">
          <span className="font-semibold text-stone-900">{request.user.name}</span> keeps their account.
          They receive your reason in IRIS and by email.
        </p>
        <div>
          <label htmlFor={reasonId} className={LABEL}>Reason</label>
          <textarea
            id={reasonId}
            required
            rows={4}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            aria-describedby={`${reasonId}-help`}
            className={fieldClasses(false)}
          />
          <p id={`${reasonId}-help`} className="mt-1 text-[13px] text-stone-600">
            The person sees this as you write it.
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

function RequestCard({
  request, onConfirm, onReject,
}: { request: AccountDeletionRequest; onConfirm: () => void; onReject: () => void }) {
  const headingId = useId();
  const blocked = request.blockers.length > 0;
  const { can_confirm: canConfirm, can_reject: canReject } = request.capabilities;
  const whyNot = blocked
    ? "Confirm is unavailable until RDCO or the person clears what's blocking it."
    : !canConfirm
      ? "You can't decide your own request. Another System Admin must."
      : null;

  return (
    <li aria-labelledby={headingId} className="bg-white rounded-xl border border-stone-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={headingId} className="text-[15px] font-semibold text-stone-900 break-words">
            {request.user.name}
          </h2>
          <p className="text-[13px] text-stone-600 break-all">
            {request.user.email}
            {request.user.role ? ` · ${request.user.role}` : ""}
          </p>
          <p className="text-[13px] text-stone-600">Asked {formatDate(request.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="secondary" onClick={onReject} disabled={!canReject}>
            Reject
          </Button>
          <Button
            type="button"
            size="sm"
            variant="danger"
            onClick={onConfirm}
            disabled={!canConfirm}
            aria-describedby={whyNot ? `${headingId}-why` : undefined}
          >
            Confirm deletion
          </Button>
        </div>
      </div>

      {blocked ? (
        <div className="mt-3">
          <h3 className="text-[13px] font-semibold text-stone-800">What's blocking it</h3>
          <ul className="mt-1 list-disc pl-5 space-y-1 text-[14px] text-stone-700">
            {request.blockers.map((b) => (
              <li key={`${b.kind}-${b.record}-${b.message}`}>{b.message}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-[14px] text-stone-700">Nothing is blocking it.</p>
      )}
      {whyNot && (
        <p id={`${headingId}-why`} className="mt-2 text-[13px] text-stone-600">{whyNot}</p>
      )}
    </li>
  );
}

export default function AccountDeletionRequestsPage() {
  const read = useApiRead(
    (signal) => accountsApi.deletionRequests({ signal }).then(({ data }) => data.results ?? []),
    [],
  );
  const requests = read.data ?? [];
  const loading = read.status === "loading";

  const [confirming, setConfirming] = useState<AccountDeletionRequest | null>(null);
  const [rejecting, setRejecting] = useState<AccountDeletionRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const closeConfirm = () => { setConfirming(null); setConfirmError(null); };

  const confirm = async () => {
    if (!confirming) return;
    setBusy(true);
    setConfirmError(null);
    try {
      await accountsApi.confirmDeletion(confirming.id);
      setDone(`${confirming.user.name}'s account was deleted.`);
      closeConfirm();
      read.retry();
    } catch (err) {
      // A stale decision or a new blocker: the server's own words, then a fresh list.
      setConfirmError(errorDetail(err, FAILED));
      read.retry();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Account Deletion Requests"
        description="People who asked for their IRIS account to be deleted."
      />

      <div className={`mb-4 ${WARNING_NOTICE}`}>
        <i className="fas fa-exclamation-triangle mt-0.5 flex-shrink-0" aria-hidden />
        <span>
          Confirming removes the person's details and private data, and they can no longer sign in.
          It <strong>can't be undone</strong>. Names on published papers and the Audit Log stay.
        </span>
      </div>

      {done && (
        <p role="status" className="mb-4 text-[14px] text-stone-700">{done}</p>
      )}

      {read.status === "interrupted" ? (
        <InterruptedState what="account deletion requests" onRetry={read.retry} />
      ) : loading && requests.length === 0 ? (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading account deletion requests" onRetry={read.retry} />
        </div>
      ) : read.status === "failed" ? (
        <LoadFailedAlert
          message={failureMessage(read.error, { lead: "The account deletion requests didn't load." })}
          onRetry={read.retry}
        />
      ) : requests.length === 0 ? (
        <EmptyState icon="fa-user-slash" title="No deletion requests" message="Nobody is waiting on a decision." />
      ) : (
        <ul aria-label="Pending account deletion requests" className="space-y-3">
          {requests.map((r) => (
            <RequestCard
              key={r.id}
              request={r}
              onConfirm={() => { setDone(null); setConfirming(r); }}
              onReject={() => { setDone(null); setRejecting(r); }}
            />
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={confirming !== null}
        title="Delete this account?"
        message={
          confirming
            ? `${confirming.user.name}'s personal details and private data will be removed and they won't be able to sign in. This can't be undone.`
            : ""
        }
        confirmLabel="Delete account"
        danger
        focusCancel
        confirming={busy}
        error={confirmError}
        onConfirm={confirm}
        onCancel={closeConfirm}
      />

      {rejecting && (
        <RejectDialog
          request={rejecting}
          onClose={() => setRejecting(null)}
          onDone={() => {
            setDone(`${rejecting.user.name}'s request was rejected. They have been told why.`);
            setRejecting(null);
            read.retry();
          }}
        />
      )}
    </div>
  );
}
