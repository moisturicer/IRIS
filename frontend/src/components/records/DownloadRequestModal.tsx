import { useId, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import { recordsApi } from "@/api/records";
import { fieldError } from "@/lib/errorDetail";
import { useUIStore } from "@/store/ui.store";

/** The longest note a reader may leave (IR-688; the server enforces it too). */
const NOTE_MAX_LENGTH = 500;

interface DownloadRequestModalProps {
  open:        boolean;
  onClose:     () => void;
  recordId:    number;
  recordTitle: string;
  /** Called after a request is submitted successfully. */
  onSubmitted?: () => void;
}

export function DownloadRequestModal({
  open,
  onClose,
  recordId,
  recordTitle,
  onSubmitted,
}: DownloadRequestModalProps) {
  const addToast = useUIStore((s) => s.addToast);
  const [submitting, setSubmitting] = useState(false);
  // Why the reader asks (IR-688): required, and shown in RDCO's queue.
  const [note, setNote] = useState("");
  const noteId = useId();
  const ready = note.trim() !== "";

  const handleSubmit = async () => {
    if (!ready) return;
    setSubmitting(true);
    try {
      await recordsApi.requestDownload(recordId, note.trim());
      addToast({
        type:    "success",
        message: "Download request sent. You will be notified when RDCO decides.",
      });
      onSubmitted?.();
      onClose();
    } catch (err: unknown) {
      const detail =
        fieldError(err, "record", "note")
        ?? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        ?? "Could not submit request. Please try again.";
      addToast({ type: "error", message: detail });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Request download access" size="max-w-md">
      <div className="space-y-4">
        <p className="text-[14px] text-gray-600 leading-relaxed">
          You are requesting permission to download documents for{" "}
          <span className="font-semibold text-gray-900">{recordTitle}</span>.
          RDCO will review your request. If they approve it, you can download the paper here
          while signed in, for a limited time.
        </p>
        <div>
          <label htmlFor={noteId} className={LABEL}>
            Why do you need a copy?
          </label>
          <textarea
            id={noteId}
            required
            rows={3}
            maxLength={NOTE_MAX_LENGTH}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-describedby={`${noteId}-help`}
            className={fieldClasses(false)}
          />
          <p id={`${noteId}-help`} className="mt-1 text-[13px] text-stone-600">
            RDCO reads this when deciding. Up to {NOTE_MAX_LENGTH} characters.
          </p>
        </div>
        <p className="text-[13px] text-gray-500 bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">
          Every copy carries your name. Do not redistribute it without permission.
        </p>
        <div className="flex gap-2 justify-end pt-1">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 rounded-lg text-[14px] font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || !ready}
            className="px-4 py-2 rounded-lg text-[14px] font-semibold text-white bg-[#6B0F12] hover:bg-[#7d1215] disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit request"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
