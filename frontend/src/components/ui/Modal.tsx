import { useEffect, type ReactNode } from "react";

interface ModalProps {
  open:     boolean;
  onClose:  () => void;
  title?:   string;
  children: ReactNode;
  /** px width class, e.g. "max-w-lg". Defaults to "max-w-lg". */
  size?:    string;
}

export function Modal({ open, onClose, title, children, size = "max-w-lg" }: ModalProps) {
  // Close on Escape key
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Panel */}
      <div
        className={`relative bg-white rounded-xl shadow-xl w-full ${size} max-h-[90vh] flex flex-col`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? "modal-title" : undefined}
      >
        {title && (
          <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
            <h2 id="modal-title" className="text-[15px] font-semibold text-gray-900">{title}</h2>
            <button
              onClick={onClose}
              className="p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100"
              aria-label="Close"
            >
              <i className="fa fa-times text-[14px]" />
            </button>
          </div>
        )}
        <div className="overflow-y-auto flex-1 p-5">
          {children}
        </div>
      </div>
    </div>
  );
}
