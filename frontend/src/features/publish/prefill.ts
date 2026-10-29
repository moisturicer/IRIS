/**
 * Prefill: the manuscript's own title and abstract, offered in Details
 * (IR-409; spec §4.5).
 *
 * The server reads the PDF with Docling after the upload, which takes from
 * seconds to minutes, so the dialog polls `metadata-suggestions` while it is
 * `pending`: every 2 s, every 5 s after 20 s, and never past 90 s. A long
 * thesis simply offers nothing in time; prefill is assistance, and Details
 * never waits on it.
 *
 * Polling runs only while the caller says it is `active` (step 2 is shown),
 * and starts again each time it becomes active. That is deliberate: a
 * retrying extraction reads `failed` between attempts (IR-406), so re-entering
 * Details after a later success still finds the suggestions.
 *
 * `generation` names the uploaded file. A replacement bumps it, which forgets
 * the old file's suggestions at once and drops any reply still in flight for
 * it, so a newer manuscript is never prefilled from an older one.
 */
import { useEffect, useState } from "react";

import { recordsApi } from "@/api/records";
import type { MetadataSuggestions } from "@/types/records";

const FAST_MS = 2000;
const SLOW_MS = 5000;
const SLOW_AFTER_MS = 20_000;
const GIVE_UP_MS = 90_000;

/**
 * `idle` before anything was asked; the server's four states; and `expired`
 * when 90 s passed while still `pending`, which shows nothing at all.
 */
export type PrefillStatus = "idle" | MetadataSuggestions["state"] | "expired";

export type Suggestions = MetadataSuggestions["suggestions"];

export interface Prefill {
  status:      PrefillStatus;
  suggestions: Suggestions;
}

export interface PrefillInput {
  recordId:   number | null;
  active:     boolean;
  generation: number;
}

const NONE: Suggestions = { title: null, abstract: null };
const IDLE: Prefill = { status: "idle", suggestions: NONE };

/** How long to wait before asking again, or null once 90 s have passed. */
export function nextPollDelay(elapsedMs: number): number | null {
  if (elapsedMs >= GIVE_UP_MS) return null;
  const base = elapsedMs < SLOW_AFTER_MS ? FAST_MS : SLOW_MS;
  return Math.min(base, GIVE_UP_MS - elapsedMs);
}

export function usePrefill({ recordId, active, generation }: PrefillInput): Prefill {
  const [result, setResult] = useState<Prefill & { generation: number }>({ ...IDLE, generation });

  useEffect(() => {
    if (!active || recordId == null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();

    async function poll(id: number) {
      let status: PrefillStatus;
      let suggestions = NONE;
      try {
        const { data } = await recordsApi.metadataSuggestions(id);
        if (cancelled) return;
        status = data.state;
        if (data.state === "ready") suggestions = data.suggestions;
      } catch {
        if (cancelled) return;
        // Assistance, not a dependency: a refused or failed request reads as
        // "couldn't read this file", never as an error state.
        status = "failed";
      }
      if (status === "pending") {
        const delay = nextPollDelay(Date.now() - started);
        if (delay == null) status = "expired";
        else timer = setTimeout(() => void poll(id), delay);
      }
      setResult({ status, suggestions, generation });
    }

    void poll(recordId);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [recordId, active, generation]);

  // A result about an earlier file is not shown even for the one render
  // before the effect above replaces it.
  return result.generation === generation ? { status: result.status, suggestions: result.suggestions } : IDLE;
}
