/**
 * Per-browser bookmarks for Calls & Conferences.
 *
 * Same deliberate limitation as `recordLibrary`: IRIS has no server-side
 * bookmark model, so this is localStorage and never syncs across devices. A
 * `SavedOpportunity` model can come later if cross-device saving turns out to
 * be wanted (IR-121 records that as the rejected-for-now alternative).
 *
 * Every surface that reads this must say so rather than implying an
 * account-level saved list.
 */

const SAVED_KEY = "iris_saved_opportunities";

function read(): number[] {
  try {
    const raw = localStorage.getItem(SAVED_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    // Defensive: a hand-edited or half-written key should degrade to "nothing
    // saved" rather than throwing on every render of the page.
    return Array.isArray(parsed) ? parsed.filter((n) => typeof n === "number") : [];
  } catch {
    return [];
  }
}

function write(ids: number[]): void {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify(ids));
  } catch {
    /* private mode or a full quota -- the page still works, saves just don't stick */
  }
}

export function getSavedOpportunityIds(): number[] {
  return read();
}

export function isOpportunitySaved(id: number): boolean {
  return read().includes(id);
}

/** Toggles and returns the new saved state, so callers need no second read. */
export function toggleSavedOpportunity(id: number): boolean {
  const ids = read();
  const next = ids.includes(id) ? ids.filter((n) => n !== id) : [...ids, id];
  write(next);
  return next.includes(id);
}
