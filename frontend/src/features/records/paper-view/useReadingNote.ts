import { isAxiosError } from "axios";
import { useCallback, useEffect, useRef, useState } from "react";

import { libraryApi } from "@/api/library";

/** The longest note the server stores, in characters (ADR-064 §4). */
export const MAX_NOTE_LENGTH = 20_000;

/** How long typing must pause before the note is saved (ADR-064 §9). */
export const NOTE_AUTOSAVE_DELAY_MS = 1000;

export type NotePhase = "idle" | "loading" | "ready" | "load_failed";
/**
 * What the reader is told. `saved` is only ever set by a save the server
 * confirmed for exactly the text now in the editor (IR-580).
 */
export type NoteStatus = "idle" | "saving" | "saved" | "failed" | "conflict";

/** The server's note when another device got there first. */
export interface NoteConflict {
  body: string;
  revision: number;
}

export interface ReadingNoteState {
  phase: NotePhase;
  text: string;
  setText: (text: string) => void;
  status: NoteStatus;
  conflict: NoteConflict | null;
  /** The editor holds text the server has not confirmed. */
  unsaved: boolean;
  /** Save again now: after a failure. */
  retry: () => void;
  /** Load again: after the note could not be loaded. */
  reload: () => void;
  /** Conflict: both texts, one after the other, saved against the server's revision. */
  keepBoth: () => void;
  /** Conflict: this device's text replaces the server's, as the reader's explicit choice. */
  keepMine: () => void;
  /** Conflict: the server's text replaces this device's draft, as the reader's explicit choice. */
  keepSaved: () => void;
}

interface Live {
  gen: number;
  recordId: number;
  phase: NotePhase;
  text: string;
  /** What the server holds, as far as this device knows. */
  saved: string;
  revision: number;
  status: NoteStatus;
  conflict: NoteConflict | null;
  inFlight: boolean;
  timer: ReturnType<typeof setTimeout> | undefined;
}

/** Whether the draft may be sent now: loaded, nothing in flight, no conflict to settle, and something unsent. */
function sendable(s: Live): boolean {
  return s.phase === "ready" && !s.inFlight && s.status !== "conflict" && s.text !== s.saved;
}

/** A note the server returned, or null for a response that is not one. */
function readNote(data: unknown): { body: string; revision: number } | null {
  const note = data as { body?: unknown; revision?: unknown } | null;
  return typeof note?.body === "string" && typeof note.revision === "number"
    ? { body: note.body, revision: note.revision }
    : null;
}

/**
 * The reader's private note on one Record, with autosave they can trust
 * (IR-580, ADR-064).
 *
 * Held by the page, not the panel, so closing the panel keeps the draft. Three
 * rules make "Saved" mean something:
 *
 * - **A write names the revision it started from.** The server refuses a stale
 *   one with its own text; this hook then pauses autosave and shows both texts,
 *   and nothing is overwritten until the reader chooses.
 * - **A failure keeps the draft** and says so; it never reports Saved.
 * - **The note is not read from `localStorage`**, and no draft is written there
 *   (ADR-044 §7: a browser-stored draft would show the next person on a shared
 *   PC what the last one wrote).
 *
 * `enabled` defers the first request until Notes is first opened. Leaving the
 * page, or moving to another Record, sends a pending draft once on the way out;
 * that last send is best effort, which is what the unsaved-leave warning is for.
 */
export function useReadingNote(
  recordId: number,
  enabled: boolean,
  delayMs: number = NOTE_AUTOSAVE_DELAY_MS,
): ReadingNoteState {
  const live = useRef<Live>({
    gen: 0, recordId, phase: "idle", text: "", saved: "", revision: 0,
    status: "idle", conflict: null, inFlight: false, timer: undefined,
  });
  const [, rerender] = useState(0);
  const publish = useCallback(() => rerender((n) => n + 1), []);
  const [loadTry, setLoadTry] = useState(0);

  const flush = useCallback(function run() {
    const s = live.current;
    clearTimeout(s.timer);
    if (!sendable(s)) return;
    const { gen } = s;
    s.inFlight = true;
    s.status = "saving";
    publish();
    libraryApi
      .saveNote(s.recordId, { body: s.text, base_revision: s.revision })
      .then((res) => {
        if (gen !== s.gen) return;
        s.inFlight = false;
        const stored = readNote(res.data);
        if (!stored) {
          // Not a note: nothing is known to be saved, so never claim it.
          s.status = "failed";
          publish();
          return;
        }
        s.saved = stored.body;
        s.revision = stored.revision;
        if (s.text === s.saved) {
          s.status = "saved";
        } else {
          // Typed on while it was in flight: that is a new save, not this one.
          s.status = "idle";
          s.timer = setTimeout(run, delayMs);
        }
        publish();
      })
      .catch((err: unknown) => {
        if (gen !== s.gen) return;
        s.inFlight = false;
        if (isAxiosError(err) && err.response?.status === 409) {
          const data = err.response.data as { body?: string; revision?: number };
          s.conflict = { body: data.body ?? "", revision: data.revision ?? 0 };
          s.status = "conflict";
        } else {
          s.status = "failed";
        }
        publish();
      });
  }, [delayMs, publish]);

  // A different Record is a different note: send what was pending for the one
  // being left, then start clean. A result that lands afterwards is ignored.
  useEffect(() => {
    const s = live.current;
    s.gen += 1;
    s.recordId = recordId;
    s.phase = "idle";
    s.text = s.saved = "";
    s.revision = 0;
    s.status = "idle";
    s.conflict = null;
    s.inFlight = false;
    publish();
    return () => {
      if (sendable(s)) {
        void libraryApi.saveNote(s.recordId, { body: s.text, base_revision: s.revision }).catch(() => undefined);
      }
      clearTimeout(s.timer);
    };
  }, [recordId, publish]);

  useEffect(() => {
    if (!enabled) return;
    const s = live.current;
    const { gen } = s;
    s.phase = "loading";
    publish();
    libraryApi
      .note(recordId)
      .then((res) => {
        if (gen !== s.gen) return;
        const stored = readNote(res.data);
        if (!stored) {
          s.phase = "load_failed";
          publish();
          return;
        }
        s.text = s.saved = stored.body;
        s.revision = stored.revision;
        s.phase = "ready";
        publish();
      })
      .catch(() => {
        if (gen !== s.gen) return;
        s.phase = "load_failed";
        publish();
      });
  }, [enabled, recordId, loadTry, publish]);

  const setText = useCallback(
    (text: string) => {
      const s = live.current;
      if (s.phase !== "ready") return;
      s.text = text;
      if (s.status === "saved") s.status = "idle";
      clearTimeout(s.timer);
      // A conflict pauses autosave: the next save is the reader's choice.
      if (s.status !== "conflict") s.timer = setTimeout(flush, delayMs);
      publish();
    },
    [delayMs, flush, publish],
  );

  const resolve = useCallback(
    (choose: (s: Live, server: NoteConflict) => void) => {
      const s = live.current;
      const server = s.conflict;
      if (!server) return;
      s.saved = server.body;
      s.revision = server.revision;
      s.conflict = null;
      s.status = "idle";
      choose(s, server);
      if (s.text === s.saved) s.status = "saved";
      publish();
      flush();
    },
    [flush, publish],
  );

  const s = live.current;
  const unsaved = s.phase === "ready" && s.text !== s.saved;
  useWarnBeforeLeaving(unsaved);
  return {
    phase: s.phase,
    text: s.text,
    setText,
    status: s.status,
    conflict: s.conflict,
    unsaved,
    retry: flush,
    reload: () => setLoadTry((n) => n + 1),
    keepBoth: () => resolve((st, server) => { st.text = `${server.body}\n\n${st.text}`; }),
    keepMine: () => resolve(() => undefined),
    keepSaved: () => resolve((st, server) => { st.text = server.body; }),
  };
}

/** Asks the browser to confirm leaving while a note holds text the server has not confirmed. */
export function useWarnBeforeLeaving(unsaved: boolean) {
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);
}
