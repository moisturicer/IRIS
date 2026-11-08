/**
 * RDCO's controls on a paper in review (ADR-051 decision 10, IR-798; the
 * endpoints are IR-797): replace the Adviser, add an owner, withdraw.
 *
 * They clear what blocks an account deletion, so they are offered on any paper
 * in review. Every control comes from `capabilities` (`replace_adviser`,
 * `add_owner`, `withdraw_paper`), so the card compares no role names, and the
 * server re-checks each act under the paper's lock.
 *
 * Each act asks first, in a dialog that says who will be told and what ends.
 * A refusal (someone else acted first, the review moved on) shows the server's
 * words and reloads the record, and the words stay on the card even when the
 * reload takes the offer away.
 */
import { useEffect, useId, useState, type ReactNode } from "react";

import { accountsApi } from "@/api/accounts";
import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import { capabilitiesFor } from "@/features/records/capabilities";
import { AdviserCombobox } from "@/features/records/metadata/AdviserCombobox";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import type { AdviserOption } from "@/types/auth";
import type { RecordDetail } from "@/types/records";

import { RailHeading } from "./headings";

/** The server's bound on a reason (`apps/records/rdco_acts.MAX_REASON_LENGTH`). */
const MAX_REASON_LENGTH = 1000;
const STAY_OPEN = () => {};

type Act = "adviser" | "owner" | "withdraw";

type Paper = Pick<RecordDetail, "id" | "capabilities" | "adviser" | "adviser_name" | "owners">;

interface RdcoPaperControlsProps {
  record: Paper;
  /** After an act or a refusal: the record's state and offers have changed. */
  onChanged: () => void;
  /** After a withdrawal: the paper is deleted, so there is nothing left to show. */
  onWithdrawn: () => void;
}

export function RdcoPaperControls({ record, onChanged, onWithdrawn }: RdcoPaperControlsProps) {
  const headingId = useId();
  const can = capabilitiesFor(record);
  const [dialog, setDialog] = useState<Act | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Kept here as well as in the dialog: a refusal reloads the record, and when
  // the offer is gone the dialog and its error go with it.
  const [refusal, setRefusal] = useState<string | null>(null);

  const offers = {
    adviser: can.has("replace_adviser"),
    owner: can.has("add_owner"),
    withdraw: can.has("withdraw_paper"),
  };
  const anyOffer = offers.adviser || offers.owner || offers.withdraw;
  // A dialog is open only while its act is still offered: a reload can take it away.
  const shown = dialog != null && offers[dialog] ? dialog : null;

  const refusalLine = refusal && shown == null && (
    <p role="alert" className="text-xs text-brand">
      {refusal}
    </p>
  );
  if (!anyOffer) return refusalLine || null;

  const open = (act: Act) => {
    setNotice(null);
    setRefusal(null);
    setDialog(act);
  };
  const done = (message: string) => {
    setDialog(null);
    setNotice(message);
    onChanged();
  };
  const refused = (message: string) => {
    setRefusal(message);
    onChanged();
  };
  const close = () => setDialog(null);

  return (
    <section
      aria-labelledby={headingId}
      className="bg-white ring-1 ring-stone-200 rounded-2xl p-5 shadow-card space-y-3"
    >
      <RailHeading id={headingId}>RDCO controls</RailHeading>
      <p className="text-xs text-stone-600">
        Change who is on this paper, or end its review. Each one tells the people it affects.
      </p>
      {notice && (
        <p role="status" className="text-xs text-stone-700">
          {notice}
        </p>
      )}
      {refusalLine}
      <div className="flex flex-wrap gap-2">
        {offers.adviser && (
          <Button type="button" variant="outline" className="min-h-11" onClick={() => open("adviser")}>
            Replace Adviser
          </Button>
        )}
        {offers.owner && (
          <Button type="button" variant="outline" className="min-h-11" onClick={() => open("owner")}>
            Add owner
          </Button>
        )}
        {offers.withdraw && (
          <Button type="button" variant="danger" className="min-h-11" onClick={() => open("withdraw")}>
            Withdraw paper
          </Button>
        )}
      </div>

      {shown === "adviser" && (
        <ReplaceAdviserDialog
          record={record}
          onCancel={close}
          onDone={(name) => done(`${name} is now the Adviser. Both Advisers have been told.`)}
          onRefused={refused}
        />
      )}
      {shown === "owner" && (
        <AddOwnerDialog
          recordId={record.id}
          onCancel={close}
          onDone={() => done("Owner added. The owners have been told.")}
          onRefused={refused}
        />
      )}
      {shown === "withdraw" && (
        <WithdrawDialog
          recordId={record.id}
          onCancel={close}
          onDone={onWithdrawn}
          onRefused={refused}
        />
      )}
    </section>
  );
}

/** The message a refusal carries: the field's own words, else `detail`. */
function refusalOf(err: unknown, field: string, fallback: string): string {
  return fieldError(err, field) ?? errorDetail(err, fallback);
}

interface ActDialogProps {
  title: string;
  verb: string;
  danger?: boolean;
  busy: boolean;
  disabled?: boolean;
  error: string | null;
  onSubmit: () => void;
  onCancel: () => void;
  children: ReactNode;
}

function ActDialog({ title, verb, danger, busy, disabled, error, onSubmit, onCancel, children }: ActDialogProps) {
  return (
    <Modal
      open
      onClose={busy ? STAY_OPEN : onCancel}
      title={title}
      size="max-w-md"
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="min-h-11" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button
            type="button"
            variant={danger ? "danger" : "primary"}
            className="min-h-11"
            onClick={onSubmit}
            loading={busy}
            disabled={disabled}
          >
            {busy ? "Please wait…" : verb}
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        {children}
        {error && (
          <p role="alert" className="text-small text-brand">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}

/** Says who hears about an act, as a list a screen reader counts. */
function WhoIsTold({ children }: { children: ReactNode }) {
  const id = useId();
  return (
    <div>
      <p id={id} className="text-sm font-semibold text-stone-800">
        Who is told
      </p>
      <ul aria-labelledby={id} className="mt-1 list-disc space-y-1 pl-5 text-sm text-stone-600">
        {children}
      </ul>
    </div>
  );
}

function useAct() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return { busy, setBusy, error, setError };
}

// --- replace the Adviser -------------------------------------------------------------

interface ReplaceAdviserDialogProps {
  record: Paper;
  onCancel: () => void;
  onDone: (name: string) => void;
  onRefused: (message: string) => void;
}

function ReplaceAdviserDialog({ record, onCancel, onDone, onRefused }: ReplaceAdviserDialogProps) {
  const pickerId = useId();
  const reasonId = useId();
  const [advisers, setAdvisers] = useState<AdviserOption[] | null>(null);
  const [listFailed, setListFailed] = useState(false);
  const [chosen, setChosen] = useState<number | undefined>(undefined);
  const [reason, setReason] = useState("");
  const { busy, setBusy, error, setError } = useAct();

  // Loaded once, when the dialog opens.
  useEffect(() => {
    let cancelled = false;
    accountsApi
      .listAdvisers()
      .then(({ data }) => {
        if (!cancelled) setAdvisers(data.results ?? []);
      })
      .catch(() => {
        if (cancelled) return;
        setAdvisers([]);
        setListFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The owners and the current Adviser can't be chosen (IR-260), so they are not offered.
  const owners = new Set(record.owners.map((o) => o.user));
  const choosable = (advisers ?? []).filter((a) => a.id !== record.adviser && !owners.has(a.id));
  const current = record.adviser_name ?? "The current Adviser";

  const submit = async () => {
    if (chosen == null) {
      setError("Choose the new Adviser.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { data } = await recordsApi.replaceAdviser(record.id, chosen, reason.trim());
      onDone(data.adviser.name);
    } catch (err) {
      const message = refusalOf(err, "adviser", "The Adviser couldn't be replaced. Try again.");
      setError(fieldError(err, "reason") ?? message);
      onRefused(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ActDialog
      title="Replace this paper's Adviser?"
      verb="Replace Adviser"
      busy={busy}
      error={error}
      onSubmit={submit}
      onCancel={onCancel}
    >
      <p className="text-sm text-stone-600">
        {current}&apos;s Adviser review ends and their open seat is withdrawn. The new Adviser takes over the
        same review, with everything filed so far, and starts it fresh.
      </p>
      <WhoIsTold>
        <li>{current}, that they were replaced and their review is closed.</li>
        <li>The new Adviser, that the review is waiting for them.</li>
      </WhoIsTold>
      <div>
        <label htmlFor={pickerId} className={LABEL}>
          New Adviser
        </label>
        {advisers == null ? (
          <p className="text-small text-stone-600">Loading advisers…</p>
        ) : listFailed ? (
          <p role="alert" className="text-small text-brand">
            The list of advisers couldn&apos;t be loaded. Close this and try again.
          </p>
        ) : (
          <AdviserCombobox
            id={pickerId}
            advisers={choosable}
            value={chosen}
            onChange={setChosen}
            selfId={null}
            required
          />
        )}
      </div>
      <div>
        <label htmlFor={reasonId} className={LABEL}>
          Reason (optional)
        </label>
        <textarea
          id={reasonId}
          rows={3}
          maxLength={MAX_REASON_LENGTH}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className={fieldClasses(false)}
        />
      </div>
    </ActDialog>
  );
}

// --- add an owner --------------------------------------------------------------------

interface AddOwnerDialogProps {
  recordId: number;
  onCancel: () => void;
  onDone: () => void;
  onRefused: (message: string) => void;
}

function AddOwnerDialog({ recordId, onCancel, onDone, onRefused }: AddOwnerDialogProps) {
  const [email, setEmail] = useState("");
  const { busy, setBusy, error, setError } = useAct();

  const submit = async () => {
    if (!email.trim()) {
      setError("Enter the new owner's email address.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await recordsApi.addOwner(recordId, email.trim());
      onDone();
    } catch (err) {
      const message = refusalOf(err, "email", "The owner couldn't be added. Try again.");
      setError(message);
      onRefused(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ActDialog title="Add an owner to this paper?" verb="Add owner" busy={busy} error={error} onSubmit={submit} onCancel={onCancel}>
      <p className="text-sm text-stone-600">
        They must already have an active, verified IRIS account. They can then see and manage the paper as
        its other owners do. The Contact person stays the same, and the review carries on.
      </p>
      <WhoIsTold>
        <li>The new owner, that they were added.</li>
        <li>The paper&apos;s current owners, who was added.</li>
      </WhoIsTold>
      <Input
        type="email"
        label="Email address"
        autoComplete="off"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        aria-invalid={Boolean(error) || undefined}
      />
    </ActDialog>
  );
}

// --- withdraw the paper --------------------------------------------------------------

interface WithdrawDialogProps {
  recordId: number;
  onCancel: () => void;
  onDone: () => void;
  onRefused: (message: string) => void;
}

function WithdrawDialog({ recordId, onCancel, onDone, onRefused }: WithdrawDialogProps) {
  const reasonId = useId();
  const helpId = useId();
  const [reason, setReason] = useState("");
  const { busy, setBusy, error, setError } = useAct();

  const submit = async () => {
    if (!reason.trim()) {
      setError("Give a reason for withdrawing the paper.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await recordsApi.rdcoWithdraw(recordId, reason.trim());
      onDone();
    } catch (err) {
      const message = refusalOf(err, "reason", "The paper couldn't be withdrawn. Try again.");
      setError(message);
      onRefused(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ActDialog
      title="Withdraw this paper?"
      verb="Withdraw paper"
      danger
      busy={busy}
      error={error}
      onSubmit={submit}
      onCancel={onCancel}
    >
      <p className="text-sm font-semibold text-stone-800">
        The paper&apos;s review stops. It is deleted and can&apos;t be restored.
      </p>
      <p className="text-sm text-stone-600">
        Every open review, revision request and document request on it closes.
      </p>
      <WhoIsTold>
        <li>Every owner, in IRIS and by email, with your reason.</li>
        <li>Each reviewer whose review closes, in IRIS.</li>
      </WhoIsTold>
      <div>
        <label htmlFor={reasonId} className={LABEL}>
          Reason
        </label>
        <textarea
          id={reasonId}
          rows={3}
          maxLength={MAX_REASON_LENGTH}
          required
          aria-required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-describedby={helpId}
          aria-invalid={Boolean(error) || undefined}
          className={fieldClasses(Boolean(error))}
        />
        <p id={helpId} className="mt-1 text-small text-stone-600">
          The owners read it as written.
        </p>
      </div>
    </ActDialog>
  );
}
