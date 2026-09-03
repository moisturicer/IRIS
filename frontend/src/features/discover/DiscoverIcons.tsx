import { useId } from "react";

/**
 * Discover icon set.
 *
 * Same two rules as the Ask IRIS set: gradient ids come from `useId()` (a
 * hard-coded `id="discoverGrad"` collides across instances and blanks every
 * copy but the first), and hues that carry meaning stay fixed — amber for
 * commercialisation, blue for IP protection — while everything else can inherit.
 */

interface IconProps {
  className?: string;
  /** Accessible name; omit when adjacent text already names the thing. */
  title?: string;
}

function a11y(title?: string) {
  return title
    ? { role: "img" as const, "aria-label": title }
    : { "aria-hidden": true as const, focusable: false as const };
}

/* ── 1. Compass emblem — the Discover surface's own mark ─────────────────── */

export function DiscoverCompassIcon({ className = "w-6 h-6", title }: IconProps) {
  const grad = `discover-grad-${useId()}`;

  return (
    <svg viewBox="0 0 48 48" className={className} fill="none" {...a11y(title)}>
      <defs>
        <linearGradient id={grad} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#8B1418" />
          <stop offset="60%" stopColor="#6B0F12" />
          <stop offset="100%" stopColor="#F59E0B" />
        </linearGradient>
      </defs>

      <circle cx="24" cy="24" r="21" stroke={`url(#${grad})`} strokeWidth="2" strokeOpacity="0.25" />
      <circle cx="24" cy="24" r="18" stroke="#6B0F12" strokeWidth="1.5" strokeDasharray="2 4" strokeOpacity="0.5" />

      {/* Cardinal ticks */}
      <line x1="24" y1="5" x2="24" y2="8" stroke="#6B0F12" strokeWidth="2" strokeLinecap="round" />
      <line x1="24" y1="40" x2="24" y2="43" stroke="#6B0F12" strokeWidth="2" strokeLinecap="round" />
      <line x1="5" y1="24" x2="8" y2="24" stroke="#6B0F12" strokeWidth="2" strokeLinecap="round" />
      <line x1="40" y1="24" x2="43" y2="24" stroke="#6B0F12" strokeWidth="2" strokeLinecap="round" />

      {/* Needle — maroon north, amber south */}
      <polygon points="24,10 28,24 24,22 20,24" fill="#6B0F12" />
      <polygon points="24,38 28,24 24,26 20,24" fill="#F59E0B" />

      <circle cx="24" cy="24" r="2.5" fill="#FFFFFF" stroke="#6B0F12" strokeWidth="1.5" />
    </svg>
  );
}

/* ── 2. Repository search — the Discover search field ────────────────────── */

export function RepositorySearchIcon({ className = "w-4 h-4", title }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y(title)}
    >
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" strokeWidth="2.5" />
      {/* Document rules inside the lens — this searches papers, not the web */}
      <line x1="7.5" y1="10" x2="14.5" y2="10" stroke="#F59E0B" strokeWidth="1.5" />
      <line x1="7.5" y1="13" x2="12" y2="13" stroke="#F59E0B" strokeWidth="1.5" />
    </svg>
  );
}

/* ── 3. KTTO commercial-ready badge ──────────────────────────────────────── */

export function CommercialReadyIcon({ className = "w-3.5 h-3.5", title }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y(title)}
    >
      <path d="M12 2a7 7 0 0 0-7 7c0 2.5 1.5 4.5 3 6h8c1.5-1.5 3-3.5 3-6a7 7 0 0 0-7-7z" fill="#FEF3C7" stroke="#D97706" />
      <path d="M9 18h6" stroke="#D97706" />
      <path d="M10 22h4" stroke="#D97706" />
      <line x1="12" y1="6.5" x2="12" y2="10.5" stroke="#B45309" strokeWidth="1.5" />
    </svg>
  );
}

/* ── 4. IP-protected shield ──────────────────────────────────────────────── */

export function IpProtectedIcon({ className = "w-3.5 h-3.5", title }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y(title)}
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="#EFF6FF" stroke="#1D4ED8" />
      <circle cx="12" cy="9" r="2" fill="#1D4ED8" stroke="none" />
      <path d="M11 11h2l1 5h-4l1-5z" fill="#1D4ED8" stroke="none" />
    </svg>
  );
}

/* ── 5. Citation marks — cite trigger and cite modal ─────────────────────── */

export function CitationIcon({ className = "w-3.5 h-3.5", title }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y(title)}
    >
      <path d="M3 11a3 3 0 0 1 3-3h1a3 3 0 0 1 3 3v4a3 3 0 0 1-3 3H5a2 2 0 0 1-2-2v-5z" fill="currentColor" fillOpacity="0.1" />
      <path d="M7 11V8a3 3 0 0 0-3-3" />
      <path d="M14 11a3 3 0 0 1 3-3h1a3 3 0 0 1 3 3v4a3 3 0 0 1-3 3h-2a2 2 0 0 1-2-2v-5z" fill="currentColor" fillOpacity="0.1" />
      <path d="M18 11V8a3 3 0 0 0-3-3" />
    </svg>
  );
}
