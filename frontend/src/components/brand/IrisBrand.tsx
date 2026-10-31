import { cn } from "@/lib/utils";
import {
  ASK,
  ASK_VIEWBOX,
  MARK,
  MARK_VIEWBOX,
  SEARCH,
  SEARCH_VIEWBOX,
  WORDMARK,
  WORDMARK_VIEWBOX,
} from "./brandPaths";

/**
 * The Folio Ribbon identity (IR-744): the IRIS mark, its lockup, the loader
 * and the two product glyphs, all traced from the approved concept artwork
 * (docs/brand/folio-ribbon/final). Everything fills with `currentColor`, so a
 * `text-brand` or `text-white` class sets the colour; the reversed versions
 * are only ever white on Binding Maroon.
 *
 * Give a mark a `title` when it is the only thing naming IRIS; leave it out
 * when adjacent text already does, and the SVG is hidden from assistive tech.
 */

interface GlyphProps {
  className?: string;
  title?: string;
}

function a11y(title?: string) {
  return title
    ? { role: "img" as const, "aria-label": title }
    : { "aria-hidden": true as const, focusable: false as const };
}

function MarkPaths() {
  return (
    <>
      <path className="iris-leaf-tl" d={MARK.leafTopLeft} />
      <path className="iris-leaf-br" d={MARK.leafBottomRight} />
      <path className="iris-ribbon-tr" d={MARK.ribbonTopRight} />
      <path className="iris-ribbon-bl" d={MARK.ribbonBottomLeft} />
    </>
  );
}

/** The mark alone: two leaves and two ribbons, with the I in the space they leave. */
export function IrisMark({ className = "h-8 w-8", title }: GlyphProps) {
  return (
    <svg viewBox={MARK_VIEWBOX} className={className} fill="currentColor" fillRule="evenodd" {...a11y(title)}>
      <MarkPaths />
    </svg>
  );
}

/** The IRIS wordmark, outlined from the concept artwork. */
export function IrisWordmark({ className = "h-4", title }: GlyphProps) {
  return (
    <svg viewBox={WORDMARK_VIEWBOX} className={className} fill="currentColor" fillRule="evenodd" {...a11y(title)}>
      <path d={WORDMARK} />
    </svg>
  );
}

/**
 * The horizontal lockup: the mark stands about 1.85 times the height of the
 * capitals, as on the concept's banner. Read as one image named by `title`.
 */
export function IrisLockup({
  className,
  markClassName = "h-9 w-9",
  wordmarkClassName = "h-5",
  title,
}: GlyphProps & { markClassName?: string; wordmarkClassName?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)} {...a11y(title)}>
      <IrisMark className={cn("shrink-0", markClassName)} />
      <IrisWordmark className={cn("w-auto shrink-0", wordmarkClassName)} />
    </span>
  );
}

/**
 * The loader: the concept board's storyboard on a 2 s loop (one leaf, its
 * partner, then the ribbons close and the I appears). Under reduced motion it
 * becomes a slow fade (see `.iris-loading` in index.css).
 *
 * With a `label` it is a polite status; without one it is decorative, for
 * callers that already announce their own loading state.
 */
export function IrisLoader({ className = "h-8 w-8 text-brand", label }: { className?: string; label?: string }) {
  const svg = (
    <svg
      viewBox={MARK_VIEWBOX}
      className={cn("iris-loading", className)}
      fill="currentColor"
      fillRule="evenodd"
      aria-hidden
      focusable={false}
    >
      <MarkPaths />
    </svg>
  );
  if (!label) return svg;
  return (
    <span role="status" aria-label={label} className="inline-flex">
      {svg}
    </span>
  );
}

/** Search: a lens cut like the folio's ribbons, and its handle. One colour. */
export function SearchGlyph({ className = "h-4 w-4", title }: GlyphProps) {
  return (
    <svg viewBox={SEARCH_VIEWBOX} className={className} fill="currentColor" fillRule="evenodd" {...a11y(title)}>
      <path d={SEARCH.lens} />
      <path d={SEARCH.handle} />
    </svg>
  );
}

const ASK_LINES = ASK.lines.split(/(?=M)/).map((d) => d.trim());

/**
 * Ask IRIS: the folio's leaves become brackets around three lines of a
 * passage. `answering` writes the lines one after another (1.8 s loop).
 */
export function AskIrisGlyph({ className = "h-5 w-5", title, answering = false }: GlyphProps & { answering?: boolean }) {
  return (
    <svg
      viewBox={ASK_VIEWBOX}
      className={cn(answering && "iris-answering", className)}
      fill="currentColor"
      fillRule="evenodd"
      {...a11y(title)}
    >
      <path d={ASK.brackets} />
      {ASK_LINES.map((d) => (
        <path key={d.slice(0, 24)} className="iris-ask-line" d={d} />
      ))}
    </svg>
  );
}
