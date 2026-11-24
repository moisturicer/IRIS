import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { cn, formatDate } from "@/lib/utils";
import { useHistoryStore } from "@/store/history.store";

const CHECKBOX = cn("h-4 w-4 shrink-0 accent-brand", FOCUS_RING);

/**
 * The reader's reading history in a pop-up (IR-1331, ADR-044 amendment
 * 2026-11-24 b), opened from the Overview's *Recently opened*, or from Saved
 * Papers for a reader with no Overview, so the tab never changes under them.
 *
 * Compact rows, like a browser's history: a tick box, the title (wrapping,
 * never cut: the Full Text Rule) and the day it was opened. A title opens the paper. The reader ticks what to
 * clear, or *Select all*, and *Clear history* asks once more before the
 * server deletes those rows. There is no pause; a history paused before
 * IR-1331 says so and can be turned back on.
 */
export function HistoryDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { items, load, keepHistory, failure, refresh, remove, setKeepHistory, dismissFailure } = useHistoryStore();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [removing, setRemoving] = useState(false);
  const selectAllRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) setSelected(new Set());
  }, [open]);

  /* A row that left the list (cleared, or gone on another device) is no longer ticked. */
  const ids = useMemo(() => items.map((i) => i.recordId), [items]);
  const chosen = useMemo(() => ids.filter((id) => selected.has(id)), [ids, selected]);
  const all = ids.length > 0 && chosen.length === ids.length;

  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = chosen.length > 0 && !all;
  }, [chosen.length, all]);

  const toggle = (id: number) => setSelected((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  const clear = async () => {
    setRemoving(true);
    const removed = await remove(chosen);
    setRemoving(false);
    setConfirming(false);
    if (removed) setSelected(new Set());
  };

  const loading = load === "idle" || load === "loading";
  const paused = keepHistory === false;

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        title="History"
        size="md"
        footer={items.length > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex min-h-11 items-center gap-2 text-small font-semibold text-stone-800">
              <input
                ref={selectAllRef}
                type="checkbox"
                className={CHECKBOX}
                checked={all}
                onChange={() => setSelected(all ? new Set() : new Set(ids))}
              />
              Select all
              {chosen.length > 0 && <span className="font-normal text-stone-600">({chosen.length} selected)</span>}
            </label>
            <Button
              type="button"
              variant="outline"
              size="page"
              disabled={chosen.length === 0}
              onClick={() => setConfirming(true)}
            >
              Clear history
            </Button>
          </div>
        )}
      >
        <p className="text-small text-stone-600">
          Your reading history follows your account to any device. Only you can see it.
        </p>

        {paused && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-card border border-stone-200 bg-surface px-3 py-2">
            <p className="text-small text-stone-700">History is paused, so papers you open are not added.</p>
            <button
              type="button"
              onClick={() => void setKeepHistory(true)}
              className={cn("min-h-10 rounded-control px-2 text-small font-semibold text-brand hover:bg-stone-100", COLOUR_TRANSITION, FOCUS_RING)}
            >
              Turn history back on
            </button>
          </div>
        )}

        {failure && (
          <p role="alert" className="mt-3 flex flex-wrap items-center gap-x-2 rounded-card border border-stone-300 bg-surface px-3 py-2 text-small text-brand">
            {failure}
            <button type="button" onClick={dismissFailure} className={cn("ml-auto rounded-control px-2 py-1 font-semibold hover:bg-stone-100", FOCUS_RING)}>
              Dismiss
            </button>
          </p>
        )}

        <div className="mt-3 border-t border-stone-200">
          {loading ? (
            <div className="mt-3 h-24 rounded-control bg-stone-100 motion-safe:animate-pulse" aria-hidden />
          ) : load === "error" ? (
            <p className="mt-3 text-small text-stone-600">
              Could not load your history. It is safe in your account.{" "}
              <button type="button" onClick={() => void refresh()} className={cn("rounded-control font-semibold text-brand underline-offset-2 hover:underline", FOCUS_RING)}>
                Try again
              </button>
            </p>
          ) : items.length === 0 ? (
            <p className="mt-3 text-small text-stone-600">
              {paused ? "No reading history. Papers you open are not added while history is paused." : "No reading history yet. Papers you open are listed here, newest first."}
            </p>
          ) : (
            <ul aria-label="Papers you opened" className="divide-y divide-stone-200">
              {items.map((item) => {
                const title = item.available && item.record ? item.record.title : null;
                const label = title ?? "A paper you can no longer open";
                return (
                  <li key={item.recordId} className="flex min-h-11 items-center gap-3 py-1.5">
                    <input
                      type="checkbox"
                      className={CHECKBOX}
                      checked={selected.has(item.recordId)}
                      onChange={() => toggle(item.recordId)}
                      aria-label={`Select ${label}`}
                    />
                    {title ? (
                      <Link
                        to={`/records/${item.recordId}`}
                        onClick={onClose}
                        className={cn("min-w-0 flex-1 break-words rounded-control text-small font-semibold text-stone-800 hover:text-brand", COLOUR_TRANSITION, FOCUS_RING)}
                      >
                        {title}
                      </Link>
                    ) : (
                      <span className="min-w-0 flex-1 text-small italic text-stone-500">{label}</span>
                    )}
                    {item.viewedAt && (
                      <span className="shrink-0 text-label tabular-nums text-stone-500">{formatDate(item.viewedAt)}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={confirming}
        title={all ? "Clear all your history?" : `Clear ${chosen.length === 1 ? "1 paper" : `${chosen.length} papers`} from your history?`}
        message="They are removed from your account on every device. This cannot be undone."
        confirmLabel="Clear history"
        danger
        confirming={removing}
        onConfirm={() => void clear()}
        onCancel={() => setConfirming(false)}
        focusCancel
      />
    </>
  );
}
