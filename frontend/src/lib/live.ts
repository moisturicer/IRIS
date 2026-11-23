/**
 * Live updates (ADR-073, IR-1213): one hint stream per tab.
 *
 * The server sends hints, never data: `{"topics": ["reviews", "record:42"]}`.
 * A page that shows one of those topics refetches it through the normal API
 * (`useLiveRefresh`), so what it shows is exactly what a reload would show.
 *
 * The stream is `GET /api/v1/live/`, read with `fetch` so it carries the
 * `Authorization` header (`EventSource` cannot). It ends when its access token
 * expires; the next attempt answers 401, the session is refreshed through the
 * one refresh path (`refreshSession`), and the stream reopens. A refresh that
 * fails ends the session as any other request's would.
 *
 * A hint missed while disconnected costs nothing: on every reconnect after the
 * first, listeners are told to resync, and pages also refetch on focus.
 */
import { API_BASE } from "@/lib/constants";

export type LiveHintListener = (topics: string[]) => void;
type ResyncListener = () => void;

const hintListeners = new Set<LiveHintListener>();
const resyncListeners = new Set<ResyncListener>();

/** Hear every hint's topics. Returns the unsubscribe. */
export function onLiveHint(listener: LiveHintListener): () => void {
  hintListeners.add(listener);
  return () => { hintListeners.delete(listener); };
}

/** Hear when the stream reconnects, so a hint may have been missed. */
export function onLiveResync(listener: ResyncListener): () => void {
  resyncListeners.add(listener);
  return () => { resyncListeners.delete(listener); };
}

/** For tests and the stream reader: deliver one hint to every listener. */
export function emitLiveHint(topics: string[]): void {
  for (const listener of [...hintListeners]) listener(topics);
}

function emitResync(): void {
  for (const listener of [...resyncListeners]) listener();
}

/** Parse `data:` lines out of SSE text, returning the topics of each event and the unread tail. */
export function parseEvents(buffer: string): { hints: string[][]; rest: string } {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const hints: string[][] = [];
  for (const block of blocks) {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim())
      .join("");
    if (!data) continue; // a comment line: `: connected`, `: ping`
    try {
      const topics = (JSON.parse(data) as { topics?: unknown }).topics;
      if (Array.isArray(topics)) hints.push(topics.filter((t): t is string => typeof t === "string"));
    } catch {
      // Not a hint: ignored, never fatal.
    }
  }
  return { hints, rest };
}

/** 1 s doubling to 60 s, with up to 25% jitter (ADR-073 decision 6). */
export function backoffMs(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(1000 * 2 ** attempt, 60_000);
  return Math.round(base * (1 + 0.25 * random()));
}

export interface LiveDeps {
  /** The access token to open the stream with, or null when signed out. */
  token: () => string | null;
  /** A fresh access token after a 401, or null when the session is over. */
  refresh: () => Promise<string | null>;
  fetchImpl?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
}

let controller: AbortController | null = null;
let running = false;
/** Bumped by every start, so a loop a restart replaced stops instead of reconnecting (IR-1289). */
let generation = 0;

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Open the stream and keep it open until `stopLive`. Idempotent. */
export function startLive(deps: LiveDeps): void {
  if (running) return;
  running = true;
  generation += 1;
  void run(deps, generation);
}

/**
 * Close the stream and open a new one: the server picks a stream's channels
 * when it opens, so a changed role is heard only on a new stream (IR-1289).
 */
export function restartLive(deps: LiveDeps): void {
  stopLive();
  startLive(deps);
}

/** Close the stream for good: sign-out, or the session ended. */
export function stopLive(): void {
  running = false;
  controller?.abort();
  controller = null;
}

export function isLiveRunning(): boolean {
  return running;
}

async function run(
  { token, refresh, fetchImpl = fetch, sleep = defaultSleep }: LiveDeps,
  mine: number,
): Promise<void> {
  let attempt = 0;
  let connectedBefore = false;
  const current = () => running && mine === generation;
  while (current()) {
    const access = token();
    if (!access) { running = false; return; }
    controller = new AbortController();
    try {
      const response = await fetchImpl(`${API_BASE}/live/`, {
        headers: { Authorization: `Bearer ${access}`, Accept: "text/event-stream" },
        signal: controller.signal,
        credentials: "same-origin",
        cache: "no-store",
      });
      if (response.status === 401) {
        // The token expired, normally at the end of a stream: refresh and go
        // round again. A failed refresh has ended the session already.
        if (!(await refresh())) { if (current()) running = false; return; }
        continue;
      }
      if (!response.ok || !response.body) throw new Error(`live: ${response.status}`);
      attempt = 0;
      if (connectedBefore) emitResync();
      connectedBefore = true;
      await read(response.body);
    } catch {
      if (!current()) return; // stopped or replaced on purpose: the abort lands here
    }
    if (!current()) return;
    await sleep(backoffMs(attempt));
    attempt += 1;
  }
}

async function read(body: ReadableStream<Uint8Array>): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const { hints, rest } = parseEvents(buffer);
    buffer = rest;
    for (const topics of hints) emitLiveHint(topics);
  }
}
