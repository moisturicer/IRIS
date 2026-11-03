/**
 * Prefill: what the server has read from the manuscript, for Details
 * (IR-409; IR-833).
 *
 * The server reads the PDF after the upload, which takes from seconds to many
 * minutes, so the dialog asks `metadata-suggestions` while it is `pending`
 * (queued, reading or retrying), backing off from every 2 s to every 15 s.
 * After two minutes it stops asking and says `stalled`: the reading is still
 * going, and *Check again* (`checkAgain`) starts asking afresh. This replaces
 * IR-409's 90-second limit, after which a long thesis silently offered
 * nothing. Prefill is assistance, and Details never waits on it.
 *
 * Polling runs only while the caller says it is `active` (step 2 is shown),
 * and starts again each time it becomes active, so reopening a draft resumes.
 *
 * `generation` names the uploaded file. A replacement bumps it when it
 * begins, which forgets the old file's reading at once and drops any reply
 * still in flight for it, so a newer manuscript is never prefilled from an
 * older one — and a refused replacement is asked about afresh, which reads
 * the manuscript the server kept.
 */
import { useCallback, useEffect, useState } from "react";

import { recordsApi } from "@/api/records";
import type { SuggestionFields } from "@/types/records";

import { NO_FIELDS, fieldsOf } from "./autofill";

const FIRST_MS = 2000;
const BACKOFF = 1.5;
const LONGEST_MS = 15_000;
const BUDGET_MS = 120_000;

/**
 * `idle` before anything was asked; the server's four states; and `stalled`
 * when the foreground budget ran out while still `pending`.
 */
export type PrefillStatus = "idle" | "pending" | "ready" | "failed" | "unsupported" | "stalled";

export interface Prefill {
  status:    PrefillStatus;
  fields:    SuggestionFields;
  /** The manuscript revision this reading is of; null before one arrives. */
  revision:  string | null;
  /** `queued`, `reading`, `retrying`, … while pending. */
  phase:     string | null;
  /** A failed reading the author may ask to retry. */
  retryable: boolean;
  /** Ask again now, with a fresh budget. */
  checkAgain: () => void;
}

export interface PrefillInput {
  recordId:   number | null;
  active:     boolean;
  generation: number;
}

type Reading = Omit<Prefill, "checkAgain">;

const IDLE: Reading = { status: "idle", fields: NO_FIELDS, revision: null, phase: null, retryable: false };

/**
 * How long to wait before asking again, or null once the budget is spent.
 * `attempt` counts the replies so far.
 */
export function nextPollDelay(attempt: number, elapsedMs: number): number | null {
  if (elapsedMs >= BUDGET_MS) return null;
  const base = Math.min(FIRST_MS * BACKOFF ** attempt, LONGEST_MS);
  return Math.min(Math.round(base), BUDGET_MS - elapsedMs);
}

export function usePrefill({ recordId, active, generation }: PrefillInput): Prefill {
  const [result, setResult] = useState<Reading & { key: string }>({ ...IDLE, key: "" });
  // Bumped by Check again, which restarts the effect below.
  const [round, setRound] = useState(0);
  const key = `${generation}:${round}`;

  useEffect(() => {
    if (!active || recordId == null) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    let attempt = 0;

    async function poll(id: number) {
      let reading: Reading;
      try {
        const { data } = await recordsApi.metadataSuggestions(id);
        if (cancelled) return;
        reading = {
          status: data.state,
          fields: data.state === "ready" ? fieldsOf(data) : NO_FIELDS,
          revision: data.manuscript_revision ?? null,
          phase: data.phase ?? null,
          retryable: Boolean(data.retryable),
        };
      } catch {
        if (cancelled) return;
        // Assistance, not a dependency: a refused or failed request reads as
        // "couldn't read this file", never as an error state.
        reading = { ...IDLE, status: "failed" };
      }
      if (reading.status === "pending") {
        const delay = nextPollDelay(attempt++, Date.now() - started);
        if (delay == null) reading = { ...reading, status: "stalled" };
        else timer = setTimeout(() => void poll(id), delay);
      }
      setResult({ ...reading, key });
    }

    void poll(recordId);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [recordId, active, key]);

  const checkAgain = useCallback(() => setRound((n) => n + 1), []);

  // A reading of an earlier file is not shown even for the one render before
  // the effect above replaces it. Check again keeps showing the last reading
  // until the new one arrives.
  const current = result.key.split(":")[0] === String(generation) ? result : IDLE;
  return { ...current, checkAgain };
}
