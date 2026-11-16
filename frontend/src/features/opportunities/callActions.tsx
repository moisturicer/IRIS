/**
 * What the Call screens share (IR-765): the board, RDCO's Call Requests and a
 * poster's My Calls load a list, report a failed act, toggle Featured and
 * delete a Call the same way, so they say the same things in the same places.
 * Every outcome is a toast (DESIGN.md §Toasts); nothing grows inside a list.
 */
import { useCallback, useEffect, useState } from "react";

import { opportunitiesApi } from "@/api/opportunities";
import { Button } from "@/components/ui/Button";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import type { Opportunity } from "@/types/opportunities";

import { callFailure, type CallFailure } from "./callFailure";

/** Who a Call's poster is, in words, for a dialog addressed to them. */
export const posterOf = (o: Opportunity) => o.posted_by_name || "The Adviser";

/** A list of Calls read once, with its loading and failed states. */
export function useCallList(read: () => Promise<Opportunity[]>) {
  const [items,   setItems]   = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed,  setFailed]  = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setFailed(false);
    read()
      .then((rows) => { if (!cancelled) setItems(rows); })
      .catch(() => { if (!cancelled) setFailed(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [read]);

  useEffect(() => load(), [load]);

  return { items, setItems, loading, failed, load };
}

/**
 * Report a failed act on a Call as a toast. A stale one (the Call changed,
 * was decided or is gone) shows the server's words, stays until dismissed and
 * reloads; anything else offers Try again when `retry` is given.
 */
export function useReportCallFailure(reload: () => void) {
  const addToast = useUIStore((s) => s.addToast);
  return useCallback((err: unknown, lead: string, retry?: () => void): CallFailure => {
    const failure = callFailure(err, lead);
    addToast(failure.stale || !retry
      ? { type: "error", persist: true, message: failure.message }
      : { type: "error", message: failure.message, action: { label: "Try again", onClick: retry } });
    if (failure.stale) reload();
    return failure;
  }, [addToast, reload]);
}

/**
 * RDCO sets or clears Featured (ADR-050 decision 12). `onChanged` receives
 * the server's copy, which carries the new `updated_at` a decision must name.
 */
export function useFeaturedToggle(onChanged: (call: Opportunity) => void, report: ReturnType<typeof useReportCallFailure>) {
  const addToast = useUIStore((s) => s.addToast);
  const [featuringId, setFeaturingId] = useState<number | null>(null);

  const toggle = async (target: Opportunity): Promise<void> => {
    setFeaturingId(target.id);
    try {
      const { data } = await opportunitiesApi.setFeatured(target.id, !target.is_featured);
      onChanged(data);
      addToast({ type: "success", message: data.is_featured ? `${data.title} is Featured.` : `${data.title} is no longer Featured.` });
    } catch (err) {
      report(err, `Could not change Featured on ${target.title}.`, () => void toggle(target));
    } finally {
      setFeaturingId(null);
    }
  };

  return { toggle, featuringId };
}

/** The Featured control: a pressed star, offered only where `can_feature` says. */
export function FeaturedToggle({ call, busy, onToggle, className }: {
  call: Opportunity; busy: boolean; onToggle: () => void; className?: string;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={onToggle}
      disabled={busy}
      aria-pressed={call.is_featured}
      aria-label={`Featured: ${call.title}`}
      className={cn(FOCUS_RING, className)}
    >
      <i className={cn(call.is_featured ? "fas" : "far", "fa-star")} aria-hidden="true" />
      Featured
    </Button>
  );
}

/**
 * Plain delete of a Call the reader has confirmed in a dialog. The dialog
 * closes either way; Try again repeats the delete already decided on.
 */
export function useDeleteCall(onDeleted: (call: Opportunity) => void, report: ReturnType<typeof useReportCallFailure>) {
  const addToast = useUIStore((s) => s.addToast);
  const [deleting, setDeleting] = useState<Opportunity | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (target: Opportunity): Promise<void> => {
    setBusy(true);
    try {
      await opportunitiesApi.remove(target.id);
      onDeleted(target);
      addToast({ type: "success", message: `${target.title} deleted.` });
    } catch (err) {
      report(err, `Could not delete ${target.title}.`, () => void run(target));
    } finally {
      setBusy(false);
      setDeleting(null);
    }
  };

  return {
    deleting,
    busy,
    ask: setDeleting,
    cancel: () => setDeleting(null),
    confirm: () => { if (deleting && !busy) void run(deleting); },
  };
}
