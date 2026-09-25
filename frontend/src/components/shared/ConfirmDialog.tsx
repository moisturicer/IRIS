import { Button } from "@/components/ui/Button";

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

// The buttons are `Button`'s own variants (IR-359), so a destructive confirm
// carries the same maroon, glyph and named verb here as anywhere else.
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
        <h3 className="text-[15px] font-bold text-stone-900 mb-2">{title}</h3>
        <p className="text-[13px] text-stone-600 mb-6">{message}</p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={confirming}>
            Cancel
          </Button>
          <Button
            type="button"
            variant={danger ? "danger" : "primary"}
            onClick={onConfirm}
            loading={confirming}
          >
            {confirming ? "Please wait…" : confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
