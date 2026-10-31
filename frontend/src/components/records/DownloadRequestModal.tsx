import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { recordsApi } from "@/api/records";
import { useUIStore } from "@/store/ui.store";

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

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await recordsApi.requestDownload(recordId);
      addToast({
        type:    "success",
        message: "Download request sent. You will be notified when RDCO decides.",
      });
      onSubmitted?.();
      onClose();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { record?: string[]; detail?: string } } }).response?.data
          ?.record?.[0]
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
            disabled={submitting}
            className="px-4 py-2 rounded-lg text-[14px] font-semibold text-white bg-[#6B0F12] hover:bg-[#7d1215] disabled:opacity-50"
          >
            {submitting ? "Submitting…" : "Submit request"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
