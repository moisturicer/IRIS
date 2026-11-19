/**
 * Discover's first-page images, kept for the session (IR-1241).
 *
 * The server sends each image `no-store` (IR-821), so the browser keeps
 * nothing. This map is what makes going back to Discover free: each record's
 * image is read once per session, and so is the answer that it has none.
 *
 * - **"None" is remembered, "pending" is not.** A 404 means there is no image
 *   to draw; a 202 means a worker is drawing it, so the next time the row
 *   appears it asks again. Nothing here polls (ADR-061).
 * - **One session only.** The map is emptied, and every object URL revoked,
 *   the moment `sessionEpoch` moves (sign-in, sign-out, session end), so the
 *   next person on a shared PC is shown nothing of the last one's.
 * - **Fenced.** A read started in one session and answered in the next is
 *   dropped, never stored.
 *
 * Memory only: nothing touches `localStorage` (ADR-044 §7).
 */
import { useAuthStore } from "@/store/auth.store";

/** An object URL for the image, or `null`: the record has none. */
type Known = string | null;

const known = new Map<number, Known>();

/** The session a read starts in, to pass back when it is answered. */
export function firstPageSession(): number {
  return useAuthStore.getState().sessionEpoch;
}

/** What this session knows: a URL, `null` for none, `undefined` if never asked. */
export function knownFirstPage(recordId: number): Known | undefined {
  return known.get(recordId);
}

/** Keep ``image`` for the session and return its URL, unless the session moved. */
export function rememberFirstPage(recordId: number, image: Blob, session: number): string | undefined {
  if (session !== firstPageSession()) return undefined;
  const already = known.get(recordId);
  if (already) return already;
  const url = URL.createObjectURL(image);
  known.set(recordId, url);
  return url;
}

/** Remember that ``recordId`` has no image, unless the session moved. */
export function rememberNoFirstPage(recordId: number, session: number): void {
  if (session !== firstPageSession()) return;
  if (!known.has(recordId)) known.set(recordId, null);
}

/** Forget everything and revoke every URL. Called on every session change. */
export function forgetFirstPages(): void {
  for (const url of known.values()) if (url) URL.revokeObjectURL(url);
  known.clear();
}

useAuthStore.subscribe((state, previous) => {
  if (state.sessionEpoch !== previous.sessionEpoch) forgetFirstPages();
});
