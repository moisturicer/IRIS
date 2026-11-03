/**
 * Details saves itself while the author works (IR-833; IR-830 decision 16).
 *
 * A change is saved a moment after the author stops, one save at a time, the
 * latest values winning. Every save names the draft revision it was made from
 * (`expected_details_revision`, added by the caller), so a save from an older
 * view — another tab, or this tab before another tab saved — is refused by
 * the server with `409 stale_edit` instead of overwriting the newer edit. The
 * hook then stops saving and says so; it never retries a conflict on its own.
 *
 * `payload` holds only what can be saved now: a field that does not pass
 * validation waits for Continue, which reports it in place. `complete` is
 * everything Continue would send, so the status says "saved" only when every
 * field of it has reached the server, and "unsaved" otherwise.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type SaveStatus = "idle" | "saving" | "saved" | "unsaved" | "failed" | "conflict";

type Body = Record<string, unknown>;

const QUIET_MS = 1500;

export interface AutosaveInput {
  enabled:  boolean;
  payload:  Body;
  complete: Body;
  save:     (payload: Body) => Promise<void>;
}

export function isStaleEdit(err: unknown): boolean {
  const response = (err as { response?: { status?: number; data?: { code?: string } } })?.response;
  return response?.status === 409 && response.data?.code === "stale_edit";
}

const differs = (body: Body, saved: Map<string, string>) =>
  Object.entries(body).some(([key, value]) => saved.get(key) !== JSON.stringify(value ?? null));

export function useAutosave({ enabled, payload, complete, save }: AutosaveInput) {
  const [status, setStatus] = useState<Exclude<SaveStatus, "unsaved">>("idle");
  // What the server holds, field by field; empty until the draft is known.
  const saved = useRef<Map<string, string> | null>(null);
  const inFlight = useRef<Promise<void> | null>(null);
  const conflicted = useRef(false);
  const latest = useRef(payload);
  latest.current = payload;
  const saveRef = useRef(save);
  saveRef.current = save;

  /** The server now holds `body`: the draft as loaded, or a save made elsewhere. */
  const markSaved = useCallback((body: Body) => {
    const map = saved.current ?? new Map<string, string>();
    for (const [key, value] of Object.entries(body)) map.set(key, JSON.stringify(value ?? null));
    saved.current = map;
  }, []);

  const saveNow = useCallback(async (): Promise<void> => {
    while (inFlight.current) await inFlight.current;
    const body = latest.current;
    if (conflicted.current || !saved.current || !differs(body, saved.current)) return;
    setStatus("saving");
    const attempt = (async () => {
      try {
        await saveRef.current(body);
        markSaved(body);
        setStatus("saved");
      } catch (err) {
        if (isStaleEdit(err)) conflicted.current = true;
        setStatus(isStaleEdit(err) ? "conflict" : "failed");
      }
    })();
    inFlight.current = attempt;
    try {
      await attempt;
    } finally {
      inFlight.current = null;
    }
  }, [markSaved]);

  const text = JSON.stringify(payload);
  useEffect(() => {
    if (!enabled || conflicted.current || !saved.current || !differs(latest.current, saved.current)) return;
    const timer = setTimeout(() => void saveNow(), QUIET_MS);
    return () => clearTimeout(timer);
  }, [enabled, text, saveNow]);

  /**
   * Run the caller's own save in the queue: after any save under way, and with
   * none starting until it ends, so the two never name the same revision.
   */
  const exclusive = useCallback(async <R,>(task: () => Promise<R>): Promise<R> => {
    while (inFlight.current) await inFlight.current;
    const attempt = task();
    const settled = attempt.then(() => undefined, () => undefined);
    inFlight.current = settled;
    try {
      return await attempt;
    } finally {
      if (inFlight.current === settled) inFlight.current = null;
    }
  }, []);

  /** The caller's own save met a newer revision. */
  const conflict = useCallback(() => {
    conflicted.current = true;
    setStatus("conflict");
  }, []);

  /** The draft was reloaded: start again from what the server holds now. */
  const reset = useCallback((body: Body) => {
    conflicted.current = false;
    saved.current = null;
    markSaved(body);
    setStatus("idle");
  }, [markSaved]);

  const unsaved = saved.current != null && differs(complete, saved.current);
  const shown: SaveStatus = (status === "saved" || status === "idle") && unsaved ? "unsaved" : status;
  return { status: shown, markSaved, saveNow, exclusive, conflict, reset };
}
