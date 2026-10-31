import { AskIrisGlyph } from "@/components/brand/IrisBrand";
import { cn } from "@/lib/utils";

/**
 * Ask IRIS icon set.
 *
 * The emblem, the assistant mark and the synthesis state are the Folio Ribbon
 * Ask IRIS icon (IR-744): the folio's leaves as brackets around three lines of
 * a passage, drawn in `currentColor`.
 *
 * The line icons that remain (the grounded citation) stroke with
 * `currentColor` instead of a baked `#6B0F12`, so they stay legible on maroon
 * message bubbles and dark surfaces.
 *
 * The amber accent that used to mark AI affordances is gone (IR-356): the
 * interface is white, black, grey and maroon, so the emblem's accents are
 * maroon shades and a pale maroon tint, and the line icons' accents follow
 * `currentColor`. The "IRIS AI" label, not a hue, is what marks AI content.
 */

interface IconProps {
  className?: string;
  /** Give the icon an accessible name; omit it when adjacent text already names the thing. */
  title?: string;
}

function a11y(title?: string) {
  return title
    ? { role: "img" as const, "aria-label": title }
    : { "aria-hidden": true as const, focusable: false as const };
}

/* ── 1. Primary emblem — assistant avatar, empty state, launcher ─────────── */

/** The Folio Ribbon Ask IRIS icon at emblem size, in Binding Maroon (IR-744). */
export function AskIrisEmblem({ className = "w-6 h-6", title }: IconProps) {
  return <AskIrisGlyph className={cn("text-brand", className)} title={title} />;
}

/* ── 2. Assistant mark — chat header, bot bubbles, nav ───────────────────── */

/** The Folio Ribbon Ask IRIS icon in the current colour (IR-744). */
export function AskIrisMark({ className = "w-5 h-5", title }: IconProps) {
  return <AskIrisGlyph className={className} title={title} />;
}

/* ── 3. Verified citation — a source that resolves to a real record ──────── */

export function GroundedCitationIcon({ className = "w-4 h-4", title }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y(title)}
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="currentColor" fillOpacity="0.07" />
      <polyline points="14 2 14 8 20 8" />
      {/* Emerald check is the one hue that must not inherit — "verified" reads
          as green regardless of the surrounding text colour. */}
      <path d="M8.75 13.25l2.25 2.25 4.25-4.25" stroke="#6B0F12" strokeWidth="2.2" />
    </svg>
  );
}

/* ── 4. Synthesis — shown while a query is being answered ────────────────── */

/**
 * While an answer is being written, the Ask IRIS icon writes its three lines
 * one after another (IR-744); it fades instead under reduced motion.
 */
export function SynthesisIcon({
  className = "w-4 h-4",
  title,
  spinning = false,
}: IconProps & { spinning?: boolean }) {
  return <AskIrisGlyph className={className} title={title} answering={spinning} />;
}
