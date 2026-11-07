/**
 * An Unlisted paper on Paper View, and RDCO's act that publishes it later
 * (ADR-047 §10, IR-878).
 *
 * Unlisted is a Thesis/Research or Project RDCO accepted and kept out of
 * Discover, for example ahead of a patent filing. Any RDCO member may publish
 * it once its embargo is released; a person ends an embargo on purpose, so
 * publishing never releases one itself.
 *
 * The card follows the server alone: it shows when `publish_unlisted` is
 * offered, and while the embargo holds, *Publish to Discover* stays disabled
 * with the server's reason beside it, so RDCO sees what to do first.
 */
import { useId, useState } from "react";

import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import { capabilitiesFor } from "@/features/records/capabilities";
import { errorDetail, fieldError } from "@/lib/errorDetail";
import type { RecordDetail } from "@/types/records";

import { RailHeading } from "./headings";

/** The server's bound on the note (`apps/records/unlisted.MAX_NOTE_LENGTH`). */
const MAX_NOTE_LENGTH = 1000;
const PUBLISHED = "Published. It is now in Discover.";
const STAY_OPEN = () => {};

interface UnlistedCardProps {
  record: Pick<RecordDetail, "id" | "record_type_name" | "capabilities" | "publish_unlisted">;
  /** After the act, or a refusal: the record's state and offers have changed. */
  onChanged: () => void;
}

export function UnlistedCard({ record, onChanged }: UnlistedCardProps) {
  const headingId = useId();
  const reasonId = useId();
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // The last refusal, kept here as well as in the dialog: a refusal reloads the
  // record, and when someone else published it first the offer, the dialog and
  // its error go with it.
  const [refusal, setRefusal] = useState<string | null>(null);

  const offer = record.publish_unlisted;
  const noticeLine = notice && (
    <p role="status" className="text-xs text-stone-700">
      {notice}
    </p>
  );
  if (!offer || !capabilitiesFor(record).has("publish_unlisted")) {
    // What happened outlives the offer: once published, the paper is no longer Unlisted.
    if (refusal) {
      return (
        <p role="alert" className="text-xs text-brand">
          {refusal}
        </p>
      );
    }
    return noticeLine || null;
  }
  const kind = record.record_type_name === "Project" ? "project" : "thesis";

  return (
    <section
      aria-labelledby={headingId}
      className="bg-white ring-1 ring-stone-200 rounded-2xl p-5 shadow-card space-y-3"
    >
      <RailHeading id={headingId}>Unlisted</RailHeading>
      {noticeLine}
      <p className="text-xs text-stone-600">
        RDCO accepted this {kind} and kept it out of Discover and Ask IRIS. RDCO can publish it once its
        embargo is released.
      </p>
      {offer.blocked && (
        <p id={reasonId} className="text-xs font-semibold text-stone-800">
          {offer.blocked}
        </p>
      )}
      <Button
        type="button"
        variant="outline"
        className="min-h-11"
        disabled={offer.blocked != null}
        aria-describedby={offer.blocked ? reasonId : undefined}
        onClick={() => setOpen(true)}
      >
        Publish to Discover
      </Button>
      <PublishUnlistedDialog
        open={open}
        recordId={record.id}
        kind={kind}
        onCancel={() => setOpen(false)}
        onPublished={() => {
          setOpen(false);
          setRefusal(null);
          setNotice(PUBLISHED);
          onChanged();
        }}
        onRefused={(message) => {
          setRefusal(message);
          onChanged();
        }}
      />
    </section>
  );
}

interface PublishUnlistedDialogProps {
  open: boolean;
  recordId: number;
  kind: string;
  onCancel: () => void;
  onPublished: () => void;
  /** A refusal may mean the offer is stale, so the record is read again. */
  onRefused: (message: string) => void;
}

function PublishUnlistedDialog({ open, recordId, kind, onCancel, onPublished, onRefused }: PublishUnlistedDialogProps) {
  const noteId = useId();
  const helpId = useId();
  const [note, setNote] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setError(null);
    onCancel();
  };
  const publish = async () => {
    setPublishing(true);
    setError(null);
    try {
      await recordsApi.publishUnlisted(recordId, note.trim());
      setNote("");
      onPublished();
    } catch (err) {
      const message = fieldError(err, "note") ?? errorDetail(err, "It couldn't be published. Try again.");
      setError(message);
      onRefused(message);
    } finally {
      setPublishing(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={publishing ? STAY_OPEN : close}
      title={`Publish this ${kind} to Discover?`}
      size="max-w-md"
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" className="min-h-11" onClick={close} disabled={publishing}>
            Cancel
          </Button>
          <Button type="button" className="min-h-11" onClick={publish} loading={publishing}>
            {publishing ? "Please wait…" : "Publish"}
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-stone-600">
          It moves from Unlisted to Discover, where any signed-in user can read it and Ask IRIS can cite it.
          Its review stays closed, and its owners and Adviser are told.
        </p>
        <div>
          <label htmlFor={noteId} className={LABEL}>
            Note (optional)
          </label>
          <textarea
            id={noteId}
            rows={3}
            maxLength={MAX_NOTE_LENGTH}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-describedby={helpId}
            aria-invalid={Boolean(error) || undefined}
            className={fieldClasses(false)}
          />
          <p id={helpId} className="mt-1 text-small text-stone-600">
            The owners and the Adviser read it in their notice, as written.
          </p>
        </div>
        {error && (
          <p role="alert" className="text-small text-brand">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
