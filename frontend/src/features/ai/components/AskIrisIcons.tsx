import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * Ask IRIS icon set.
 *
 * Two deliberate departures from the original drafts:
 *
 * 1. Gradient and filter ids come from `useId()`. Hard-coding `id="irisGrad"`
 *    breaks the moment two instances render on one page — SVG ids are global,
 *    the browser resolves `url(#irisGrad)` to whichever node is first in the
 *    document, and unmounting that one blanks every other instance.
 * 2. The line icons stroke with `currentColor` instead of a baked `#6B0F12`,
 *    so they stay legible on maroon message bubbles and dark surfaces. The
 *    amber accent is kept as the one fixed hue — it is the "intelligence"
 *    signal that separates AI affordances from ordinary record chrome.
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

export function AskIrisEmblem({ className = "w-6 h-6", title }: IconProps) {
  const uid = useId();
  const grad = `iris-grad-${uid}`;
  const glow = `iris-glow-${uid}`;

  return (
    <svg viewBox="0 0 48 48" className={className} fill="none" {...a11y(title)}>
      <defs>
        <linearGradient id={grad} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#8B1418" />
          <stop offset="50%" stopColor="#6B0F12" />
          <stop offset="100%" stopColor="#F59E0B" />
        </linearGradient>
        <filter id={glow} x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Orbital rings — the corpus the assistant reasons over */}
      <circle
        cx="24" cy="24" r="20"
        stroke={`url(#${grad})`} strokeWidth="1.5" strokeDasharray="4 3" opacity="0.4"
      />
      <circle
        cx="24" cy="24" r="15"
        stroke="#F59E0B" strokeWidth="1" strokeDasharray="2 4" opacity="0.6"
      />

      {/* Quad-point intelligence star */}
      <path
        d="M24 6 C24 16, 16 24, 6 24 C16 24, 24 32, 24 42 C24 32, 32 24, 42 24 C32 24, 24 16, 24 6 Z"
        fill={`url(#${grad})`}
        filter={`url(#${glow})`}
      />

      {/* Satellite sparkles + core highlight */}
      <circle cx="36" cy="12" r="2" fill="#F59E0B" />
      <circle cx="12" cy="36" r="1.5" fill="#FCD34D" />
      <circle cx="24" cy="24" r="3" fill="#FFFFFF" opacity="0.9" />
    </svg>
  );
}

/* ── 2. Assistant mark — chat header, bot bubbles, nav ───────────────────── */

export function AskIrisMark({ className = "w-5 h-5", title }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y(title)}
    >
      {/* Core */}
      <path
        d="M12 2a4 4 0 0 1 4 4c0 1.5-.8 2.8-2 3.5v1.5h-4v-1.5C8.8 8.8 8 7.5 8 6a4 4 0 0 1 4-4z"
        fill="currentColor"
        fillOpacity="0.12"
      />
      {/* Synaptic stem */}
      <path d="M10 11h4v3a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-3z" />
      <path d="M6.5 18h11" />
      <path d="M9 21.5h6" />
      {/* Sparkle rays — the fixed amber accent */}
      <line x1="2.5" y1="6" x2="4.5" y2="6" stroke="#F59E0B" strokeWidth="1.8" />
      <line x1="19.5" y1="6" x2="21.5" y2="6" stroke="#F59E0B" strokeWidth="1.8" />
      <line x1="3.9" y1="3.6" x2="5.1" y2="4.8" stroke="#F59E0B" strokeWidth="1.5" />
      <line x1="20.1" y1="3.6" x2="18.9" y2="4.8" stroke="#F59E0B" strokeWidth="1.5" />
    </svg>
  );
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
      <path d="M8.75 13.25l2.25 2.25 4.25-4.25" stroke="#10B981" strokeWidth="2.2" />
    </svg>
  );
}

/* ── 4. Synthesis — shown while a query is being answered ────────────────── */

export function SynthesisIcon({
  className = "w-4 h-4",
  title,
  spinning = false,
}: IconProps & { spinning?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn(className, spinning && "animate-spin motion-reduce:animate-none")}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y(title)}
    >
      <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" stroke="#F59E0B" />
      <path d="M16 21h5v-5" stroke="#F59E0B" />
      <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
    </svg>
  );
}
