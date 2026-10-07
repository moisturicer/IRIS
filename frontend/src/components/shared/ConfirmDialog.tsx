import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";

interface ConfirmDialogProps {
  open:       boolean;
  title:      string;
  message:    string;
  onConfirm:  () => void;
  onCancel:   () => void;
  confirmLabel?: string;
  danger?:    boolean;
  confirming?: boolean;
  /** Why the last attempt failed, shown in the dialog so the choice stays in front of them. */
  error?:     string | null;
}

// The buttons are `Button`'s own variants (IR-359), so a destructive confirm
// carries the same maroon, glyph and named verb here as anywhere else.
//
// Built on `Modal` (IR-412, spec §4.13): a dialog labelled by its title, focus
// kept inside it, Escape to cancel, and focus back on the opener after. While
// confirming, neither Escape nor the backdrop can close it, as Cancel cannot.
export function ConfirmDialog({
  open,
  title,
  message,
  onConfirm,
  onCancel,
  confirmLabel = "Confirm",
  danger,
  confirming = false,
  error = null,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      onClose={confirming ? () => {} : onCancel}
      title={title}
      size="max-w-sm"
      footer={
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
      }
    >
      <p className="text-[14px] text-stone-600">{message}</p>
      {error && (
        <p role="alert" className="mt-3 text-small text-brand">
          {error}
        </p>
      )}
    </Modal>
  );
}
