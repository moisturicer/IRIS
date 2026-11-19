/**
 * The dialog RDCO writes a note in when it declines a request (IR-688 for
 * download requests, IR-1099 for delete requests), revokes a download grant,
 * or rejects or removes an Adviser's Call (IR-765, where it is a reason).
 * One component, so the queues ask for it the same way: a note is required, its
 * length is limited here and again by the server, and a refusal keeps what was
 * typed beside the server's reason.
 */
import { useId, useState, type FormEvent } from "react";
import { Button, Modal } from "@/components/ui";
import { FieldError } from "@/components/ui/FieldError";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { errorDetail, fieldError } from "@/lib/errorDetail";

/** The longest note RDCO may leave (IR-688; the server enforces it too). */
export const NOTE_MAX_LENGTH = 500;
/**
 * A note on a request, or a reason a Call's Adviser is sent (IR-765): what the
 * field is called, the server's limit on it, and the key it files a refusal under.
 */
const KINDS = {
  note:   { noun: "Note",   maxLength: NOTE_MAX_LENGTH, field: "note" },
  reason: { noun: "Reason", maxLength: 2000,            field: "reason" },
} as const;
export type NoteKind = keyof typeof KINDS;
/** The longest reason RDCO may give a Call's Adviser (`ReasonSerializer`). */
export const REASON_MAX_LENGTH = KINDS.reason.maxLength;

/** Shown where a decision made before notes existed has none (IR-688, IR-1099). */
export const NO_NOTE = "No note recorded";

/** RDCO's note under a decided row's status, or that there is none (older rows). */
export function RdcoNoteLine({ note }: { note: string }) {
  return (
    <p className="mt-1 text-label break-words">
      <span className="text-stone-500">RDCO's note: </span>
      {note
        ? <span className="text-stone-700">{note}</span>
        : <span className="text-stone-500 italic">{NO_NOTE}</span>}
    </p>
  );
}

type Props = {
  title: string;
  /** The button that sends it, e.g. "Decline". */
  submitLabel: string;
  /** Who the note goes to, e.g. "reader": "Note to the reader". */
  audience: string;
  /** The request being decided: who asked, and about what. */
  requester: string;
  recordTitle: string;
  /** What happens once it is sent. */
  intro: string;
  send: (note: string) => Promise<unknown>;
  onClose: () => void;
  onDone: () => void;
  /** A note on a request (default), or a reason for a Call (IR-765). */
  kind?: NoteKind;
  /**
   * Report a failure that isn't about the text itself outside the dialog, as
   * a toast, instead of in a box that grows inside it (IR-765). Answer "keep"
   * to leave the dialog open with what was typed, or "close". A refusal of the
   * text itself always shows under the field.
   */
  onFailure?: (err: unknown) => "keep" | "close";
};

export function RdcoNoteDialog({
  title, submitLabel, audience, requester, recordTitle, intro, send, onClose, onDone,
  kind = "note", onFailure,
}: Props) {
  const { noun, maxLength, field } = KINDS[kind];
  const ids = useId();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [textError, setTextError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const ready = note.trim() !== "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setTextError(null);
    setSending(true);
    try {
      await send(note.trim());
      onDone();
    } catch (err) {
      const aboutText = fieldError(err, field);
      if (onFailure) {
        // The text's own refusal belongs under the text; anything else is a toast.
        if (aboutText) setTextError(aboutText);
        else if (onFailure(err) === "close") onClose();
        return;
      }
      // The note stays in the box beside the server's reason.
      setError(aboutText ?? errorDetail(err, "That did not go through. Please try again."));
    } finally {
      setSending(false);
    }
  };

  const formId = `${ids}-form`;
  const noteId = `${ids}-note`;

  return (
    <Modal
      open
      onClose={sending ? () => {} : onClose}
      title={title}
      footer={
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={sending}>
            Cancel
          </Button>
          <Button type="submit" form={formId} variant="danger" disabled={!ready} loading={sending}>
            {submitLabel}
          </Button>
        </div>
      }
    >
      <form id={formId} onSubmit={submit} noValidate className="space-y-4">
        <p className="text-sm text-stone-700 leading-relaxed">
          <span className="font-semibold text-stone-900">{requester}</span>
          {" · "}
          {recordTitle}. {intro}
        </p>
        <div>
          <label htmlFor={noteId} className={LABEL}>
            {noun} to the {audience}
          </label>
          <textarea
            id={noteId}
            required
            rows={4}
            maxLength={maxLength}
            value={note}
            onChange={(e) => { setNote(e.target.value); setTextError(null); }}
            aria-invalid={textError ? true : undefined}
            aria-describedby={textError ? `${noteId}-error` : `${noteId}-help`}
            className={fieldClasses(Boolean(textError))}
          />
          {textError
            ? <FieldError id={`${noteId}-error`}>{textError}</FieldError>
            : (
              <p id={`${noteId}-help`} className="mt-1 text-small text-stone-600">
                The {audience} sees this as you write it. Up to {maxLength.toLocaleString("en")} characters.
              </p>
            )}
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
