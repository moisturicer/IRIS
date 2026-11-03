/**
 * A paper's embargo on Paper View, and the acts that change it after submission
 * (ADR-052 decisions 5, 6 and 11).
 *
 * Every control comes from `capabilities`, so the card compares no role names.
 * A release sends text to outside AI companies for good, so it always asks first.
 */
import { useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { capabilitiesFor } from "@/features/records/capabilities";
import { manilaToday } from "@/features/publish/draft";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import { formatDate } from "@/lib/utils";
import type { RecordDetail, RecordEmbargo } from "@/types/records";

import { RailHeading } from "./headings";

const RECALL_WARNING =
  "Text already sent to outside AI companies can't be recalled. An embargo stops anything more being sent.";
const CANNOT_BE_UNDONE = "can't be undone";

function stateWording(embargo: RecordEmbargo): { label: string; detail: string | null } {
  const until = embargo.until ? formatDate(embargo.until) : null;
  switch (embargo.state) {
    case "active":
      return {
        label: "Under embargo",
        detail: `Review by ${until}. The date is a reminder: the embargo lasts until someone releases it.`,
      };
    case "released":
      return { label: "Released", detail: until ? `Its review date was ${until}.` : null };
    case "none":
      return { label: "No embargo", detail: null };
    default:
      return {
        label: "Not answered",
        detail: "Nobody has said whether this paper is under embargo, so it stays out of the AI.",
      };
  }
}

interface EmbargoCardProps {
  record: Pick<RecordDetail, "id" | "embargo" | "capabilities" | "is_ip">;
  /** After any act: the record's state and offers have changed. */
  onChanged: () => void;
  /** Manila's today, the earliest date the server accepts. */
  today?: string;
}

export function EmbargoCard({ record, onChanged, today = manilaToday() }: EmbargoCardProps) {
  const headingId = useId();
  const can = capabilitiesFor(record);
  const [dialog, setDialog] = useState<"set" | "release" | "release_ip" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const embargo = record.embargo;
  const offersIpRelease = record.is_ip && can.has("release_ip");
  if (!embargo && !offersIpRelease) return null;

  const active = embargo?.state === "active";
  const done = (message: string | null = null) => {
    setDialog(null);
    setNotice(message);
    onChanged();
  };
  const state = embargo ? stateWording(embargo) : null;

  return (
    <section
      aria-labelledby={headingId}
      className="bg-white ring-1 ring-stone-200 rounded-2xl p-5 shadow-card space-y-3"
    >
      <RailHeading id={headingId}>Embargo</RailHeading>

      {state && (
        <div>
          <p className="text-sm font-bold text-stone-900">{state.label}</p>
          {state.detail && <p className="mt-1 text-xs text-stone-600">{state.detail}</p>}
          {active && !can.has("release_embargo") && (
            <p className="mt-1 text-xs text-stone-600">Only the paper&apos;s Adviser or RDCO can release it.</p>
          )}
        </div>
      )}

      {notice && (
        <p role="status" className="text-xs text-stone-700">
          {notice}
        </p>
      )}

      {(can.has("set_embargo") || (active && can.has("release_embargo")) || offersIpRelease) && (
        <div className="flex flex-wrap gap-2">
          {can.has("set_embargo") && embargo && (
            <Button type="button" variant="outline" className="min-h-11" onClick={() => setDialog("set")}>
              {active ? "Change date" : "Set embargo"}
            </Button>
          )}
          {active && can.has("release_embargo") && (
            <Button type="button" variant="outline" className="min-h-11" onClick={() => setDialog("release")}>
              Release embargo
            </Button>
          )}
          {offersIpRelease && (
            <Button type="button" variant="outline" className="min-h-11" onClick={() => setDialog("release_ip")}>
              Release IP mark
            </Button>
          )}
        </div>
      )}

      {embargo && (
        <SetEmbargoDialog
          open={dialog === "set"}
          recordId={record.id}
          embargo={embargo}
          today={today}
          onCancel={() => setDialog(null)}
          onSaved={(saved) => done(saved.notice ?? null)}
        />
      )}
      <ReleaseDialog
        open={dialog === "release"}
        title="Release this embargo?"
        message={
          `Its text can then be sent to outside AI companies, unless an IP mark or missing consent ` +
          `still holds it back, and this ${CANNOT_BE_UNDONE}.`
        }
        act={() => recordsApi.releaseEmbargo(record.id)}
        onCancel={() => setDialog(null)}
        onReleased={() => done()}
        onRefused={onChanged}
      />
      <ReleaseDialog
        open={dialog === "release_ip"}
        title="Release this IP mark for the AI?"
        message={
          `The paper stays marked as intellectual property, but its text can then be sent to outside AI ` +
          `companies once nothing else holds it back, and this ${CANNOT_BE_UNDONE}.`
        }
        act={() => recordsApi.releaseIp(record.id)}
        onCancel={() => setDialog(null)}
        onReleased={() => done()}
        onRefused={onChanged}
      />
    </section>
  );
}

interface ReleaseDialogProps {
  open: boolean;
  title: string;
  message: string;
  act: () => Promise<unknown>;
  onCancel: () => void;
  onReleased: () => void;
  /** A refusal may mean the offer is stale, so the record is read again. */
  onRefused: () => void;
}

function ReleaseDialog({ open, title, message, act, onCancel, onReleased, onRefused }: ReleaseDialogProps) {
  const [releasing, setReleasing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setReleasing(true);
    setError(null);
    try {
      await act();
      onReleased();
    } catch (err) {
      setError(errorDetail(err, "This couldn't be released. Try again."));
      onRefused();
    } finally {
      setReleasing(false);
    }
  };

  return (
    <ConfirmDialog
      open={open}
      title={title}
      message={message}
      confirmLabel="Release"
      danger
      focusCancel
      confirming={releasing}
      error={error}
      onConfirm={confirm}
      onCancel={() => {
        setError(null);
        onCancel();
      }}
    />
  );
}

interface SetEmbargoDialogProps {
  open: boolean;
  recordId: number;
  embargo: RecordEmbargo;
  today: string;
  onCancel: () => void;
  onSaved: (saved: RecordEmbargo) => void;
}

const STAY_OPEN = () => {};

function SetEmbargoDialog({ open, recordId, embargo, today, onCancel, onSaved }: SetEmbargoDialogProps) {
  const active = embargo.state === "active";
  const [until, setUntil] = useState(active ? (embargo.until ?? "") : "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // "No embargo" and "released" are the states in which the check may already
  // have let text out (ADR-052 IR-812 Amendment).
  const mayHaveGone = embargo.state === "none" || embargo.state === "released";

  const close = () => {
    setError(null);
    setUntil(active ? (embargo.until ?? "") : "");
    onCancel();
  };
  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const { data } = await recordsApi.setEmbargo(recordId, until);
      onSaved(data);
    } catch (err) {
      setError(fieldError(err, "embargoed_until") ?? errorDetail(err, "The date couldn't be saved. Try again."));
    } finally {
      setSaving(false);
    }
  };

  const verb = active ? "Save date" : "Set embargo";
  return (
    <Modal
      open={open}
      onClose={saving ? STAY_OPEN : close}
      title={active ? "Change the review date" : "Set an embargo"}
      size="max-w-sm"
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" className="min-h-11" onClick={close} disabled={saving}>
            Cancel
          </Button>
          <Button type="button" className="min-h-11" onClick={save} loading={saving}>
            {saving ? "Please wait…" : verb}
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-stone-600">
          The date is when to review the embargo. It doesn&apos;t end it: the Adviser or RDCO does.
        </p>
        {mayHaveGone && <p className="text-sm font-semibold text-stone-800">{RECALL_WARNING}</p>}
        <Input
          type="date"
          label="Review date"
          min={today}
          value={until}
          onChange={(e) => setUntil(e.target.value)}
          aria-invalid={Boolean(error) || undefined}
        />
        {error && (
          <p role="alert" className="text-small text-brand">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
