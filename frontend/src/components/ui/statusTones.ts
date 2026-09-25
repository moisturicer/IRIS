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
  quiet:     "bg-stone-100 text-stone-700 ring-1 ring-stone-200",
  /** With a reviewer, or recoverable. */
  active:    "bg-brand-50 text-brand ring-1 ring-brand-200",
  /** Terminal or blocking: someone must act. */
  attention: "bg-brand text-white",
  /** Finished. */
  settled:   "bg-stone-900 text-white",
} as const;

export type Tone = keyof typeof TONES;
