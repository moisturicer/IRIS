import { useEffect, useState } from "react";
import type { AccountLock } from "@/features/auth/loginFailure";

function formatCountdown(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function secondsUntil(endAt: number): number {
  return Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
}

interface AccountLockedModalProps {
  open: boolean;
  onClose: () => void;
  /** Which lock it is. It holds no duration of its own (IR-555). */
  lock: AccountLock | null;
}

/**
 * Says which lock refused the sign-in, and when it lifts only when someone
 * actually knows (IR-555): a countdown to the server's `unlock_at`, or the
 * browser's own lock's time, and no time at all for RDCO's lock, which lifts
 * only when RDCO unlocks it.
 */
export function AccountLockedModal({ open, onClose, lock }: AccountLockedModalProps) {
  const endAt = lock?.by === "attempts" ? lock.unlockAt : null;
  const [remaining, setRemaining] = useState(() => (endAt === null ? 0 : secondsUntil(endAt)));

  useEffect(() => {
    if (!open || endAt === null) return;
    const tick = () => {
      const secs = secondsUntil(endAt);
      setRemaining(secs);
      if (secs <= 0) onClose();
    };
    tick();
    const id = globalThis.setInterval(tick, 1000);
    return () => globalThis.clearInterval(id);
  }, [open, endAt, onClose]);

  if (!open || !lock) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" aria-hidden onClick={onClose} />
      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-[380px] px-8 py-8 text-center"
        role="dialog"
        aria-modal="true"
        aria-labelledby="lockout-title"
      >
        <div className="mx-auto w-14 h-14 rounded-full bg-brand-50 flex items-center justify-center mb-5">
          <svg className="w-7 h-7 text-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden>
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>

        <h2 id="lockout-title" className="text-[20px] font-bold text-stone-900">
          Account Locked
        </h2>
        <p className="mt-3 text-[15px] text-stone-600 leading-relaxed">
          {lock.by === "admin" ? (
            <>
              RDCO has locked this account, and it stays locked until they unlock it, so trying
              again won&apos;t help. Contact RDCO or your department administrator.
            </>
          ) : endAt === null ? (
            <>
              Too many failed sign-in attempts, so sign-in is paused for this account. Try again
              later, or contact RDCO or your department administrator if it stays locked.
            </>
          ) : (
            <>
              Too many failed sign-in attempts. Please try again in{" "}
              <span className="font-bold text-brand tabular-nums">{formatCountdown(remaining)}</span>
            </>
          )}
        </p>

        <button
          type="button"
          onClick={onClose}
          className="mt-8 w-full py-3 rounded-lg text-[15px] font-semibold text-stone-700
            bg-stone-100 hover:bg-stone-200 transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  );
}
