import { useEffect, useState } from "react";

const LOCKOUT_SECONDS = 15 * 60; // FR-M1-01 / SRS: 15-minute lockout

function formatCountdown(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface AccountLockedModalProps {
  open: boolean;
  onClose: () => void;
  /** Unix ms when lockout ends; defaults to now + 15 min */
  unlockAt?: number;
}

export function AccountLockedModal({ open, onClose, unlockAt }: AccountLockedModalProps) {
  const endAt = unlockAt ?? Date.now() + LOCKOUT_SECONDS * 1000;
  const [remaining, setRemaining] = useState(() =>
    Math.max(0, Math.ceil((endAt - Date.now()) / 1000))
  );

  useEffect(() => {
    if (!open) return;
    const tick = () => {
      const secs = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
      setRemaining(secs);
      if (secs <= 0) onClose();
    };
    tick();
    const id = globalThis.setInterval(tick, 1000);
    return () => globalThis.clearInterval(id);
  }, [open, endAt, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" aria-hidden onClick={onClose} />
      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-[380px] px-8 py-8 text-center"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lockout-title"
      >
        <div className="mx-auto w-14 h-14 rounded-full bg-red-100 flex items-center justify-center mb-5">
          <svg className="w-7 h-7 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>

        <h2 id="lockout-title" className="text-[20px] font-bold text-gray-900">
          Account Locked
        </h2>
        <p className="mt-3 text-[14px] text-gray-600 leading-relaxed">
          Too many failed login attempts. Please try again in{" "}
          <span className="font-bold text-red-600 tabular-nums">{formatCountdown(remaining)}</span>
        </p>

        <button
          type="button"
          onClick={onClose}
          className="mt-8 w-full py-3 rounded-lg text-[14px] font-semibold text-gray-700
            bg-gray-100 hover:bg-gray-200 transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  );
}
