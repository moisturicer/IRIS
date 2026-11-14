/**
 * The four status tones (IR-356; 01-design-system.md section 0), shared so
 * that every screen says the same thing with the same colour (IR-358).
 *
 * A tone is chosen by what a state means, never by which screen shows it, and
 * it is never the only signal: whatever wears it also carries a label, and the
 * states that stop a record carry an icon too.
 */
export const TONES = {
  /** Not yet with a reviewer. */
  quiet:     "bg-transparent text-stone-700 ring-1 ring-stone-300",
  /** With a reviewer, or recoverable. White, maroon text, Rule Stone outline (IR-1097). */
  active:    "bg-surface text-brand ring-1 ring-stone-300",
  /** Terminal or blocking: someone must act. The one filled tone. */
  attention: "bg-brand text-white",
  /** Finished. An Ink outline on white, so it never out-shouts a title (IR-1097). */
  settled:   "bg-surface text-stone-900 ring-1 ring-stone-900",
} as const;

export type Tone = keyof typeof TONES;
