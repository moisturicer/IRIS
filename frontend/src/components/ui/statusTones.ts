/**
 * The five status tones (IR-356, IR-1290; 01-design-system.md section 0),
 * shared so that every screen says the same thing with the same colour
 * (IR-358).
 *
 * A tone is chosen by what a state means, never by which screen shows it, and
 * it is never the only signal: whatever wears it also carries a label, and the
 * states that stop a record carry an icon too.
 *
 * No tone is filled (IR-1290). A solid maroon fill is the one action to take
 * next, so a status that needs someone is a maroon outline instead and can
 * never be mistaken for a button.
 */
export const TONES = {
  /** Not yet with a reviewer. */
  quiet:     "bg-transparent text-stone-700 ring-1 ring-stone-300",
  /** With a reviewer, or recoverable. Amber text and outline on white (IR-1290). */
  active:    "bg-surface text-review ring-1 ring-review-line",
  /** An office cleared it or kept its clearance. Green text and outline on white (IR-1290). */
  cleared:   "bg-surface text-cleared ring-1 ring-cleared-line",
  /** Terminal or blocking: someone must act. A maroon outline, never a fill (IR-1290). */
  attention: "bg-surface text-brand ring-[1.5px] ring-brand",
  /** Finished. An Ink outline on white, so it never out-shouts a title (IR-1097). */
  settled:   "bg-surface text-stone-900 ring-1 ring-stone-900",
} as const;

export type Tone = keyof typeof TONES;
