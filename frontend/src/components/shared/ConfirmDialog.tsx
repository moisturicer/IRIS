interface ConfirmDialogProps {
  open:       boolean;
  title:      string;
  message:    string;
  onConfirm:  () => void;
  onCancel:   () => void;
  confirmLabel?: string;
  danger?:    boolean;
  confirming?: boolean;
}

export function ConfirmDialog({
  open,
  title,
  message,
  onConfirm,
  onCancel,
  confirmLabel = "Confirm",
  danger,
  confirming = false,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6">
        <h3 className="text-[15px] font-bold text-gray-900 mb-2">{title}</h3>
        <p className="text-[13px] text-gray-600 mb-6">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={confirming}
            className="px-4 py-2 rounded-lg border border-gray-200 text-[13px] font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={confirming}
            className={`px-4 py-2 rounded-lg text-[13px] font-semibold text-white disabled:opacity-50 ${danger ? "bg-red-600 hover:bg-red-700" : "bg-[#6B0F12] hover:bg-[#7d1215]"}`}
          >
            {confirming ? "Please wait…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
