import type { ReactNode } from "react";

import { AskIrisGlyph } from "@/components/brand/IrisBrand";
import { cn } from "@/lib/utils";

/**
 * Ask IRIS icon set.
 *
 * The emblem, the assistant mark and the synthesis state are the Folio Ribbon
 * Ask IRIS icon (IR-744): a speech bubble with the mark's serif I cut out of
 * it, drawn in `currentColor`.
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
 * While an answer is being written, the Ask IRIS icon sets the I of its bubble
 * in type (IR-744); it fades instead under reduced motion.
 */
export function SynthesisIcon({
  className = "w-4 h-4",
  title,
  spinning = false,
}: IconProps & { spinning?: boolean }) {
  return <AskIrisGlyph className={className} title={title} answering={spinning} />;
}

/* ── 5. Conversations pane toggle (IR-1233) ──────────────────────────────── */

/**
 * A window with its left panel marked: the one toggle that opens and closes the
 * conversations pane. Stroked at 1.75 in `currentColor`, and decorative: the
 * button that holds it carries the name.
 */
/** The right-hand panel's icon (IR-1237): the left-panel mark, mirrored. */
export function PanelRightIcon({ className = "size-5" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y()}
    >
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M15 3v18" />
    </svg>
  );
}

export function PanelLeftIcon({ className = "size-5" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      {...a11y()}
    >
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}

/* ── 6. The outline set (IR-1235) ─────────────────────────────────────────── */

/** What every glyph of the outline set is: pass one around as `OutlineIcon`. */
export type OutlineIcon = (props: OutlineIconProps) => JSX.Element;

export interface OutlineIconProps {
  /** Colour, spacing and motion only: the size is `inline`'s to set. */
  className?: string;
  /** 16 px beside text; the default, 20 px, is for a control. */
  inline?: boolean;
}

/**
 * Every glyph below is stroked at 1.75 in `currentColor` on a 24 px grid and
 * drawn at 20 px in a control or 16 px inline. Always decorative: the button or
 * text that holds an icon carries the name. The speech bubble stays reserved
 * for Ask IRIS itself, so nothing here is a bubble.
 */
function outline(name: string, shapes: ReactNode) {
  function Icon({ className, inline = false }: OutlineIconProps) {
    return (
      <svg
        viewBox="0 0 24 24"
        className={cn("shrink-0", inline ? "size-4" : "size-5", className)}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        {...a11y()}
      >
        {shapes}
      </svg>
    );
  }
  Icon.displayName = name;
  return Icon;
}

export const PlusIcon = outline("PlusIcon", <path d="M5 12h14M12 5v14" />);
export const ArrowUpIcon = outline("ArrowUpIcon", <path d="m5 12 7-7 7 7M12 19V5" />);
export const ArrowRightIcon = outline("ArrowRightIcon", <path d="M5 12h14m-7-7 7 7-7 7" />);
export const CloseIcon = outline("CloseIcon", <path d="M18 6 6 18M6 6l12 12" />);
export const ChevronDownIcon = outline("ChevronDownIcon", <path d="m6 9 6 6 6-6" />);
export const ChevronUpIcon = outline("ChevronUpIcon", <path d="m18 15-6-6-6 6" />);
export const ChevronRightIcon = outline("ChevronRightIcon", <path d="m9 18 6-6-6-6" />);
export const CheckIcon = outline("CheckIcon", <path d="M20 6 9 17l-5-5" />);
export const RetryIcon = outline("RetryIcon", <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8M21 3v5h-5" />);
export const PencilIcon = outline(
  "PencilIcon",
  <path d="M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5zM15 5l4 4" />,
);
export const UserIcon = outline("UserIcon", <><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></>);
export const SearchIcon = outline("SearchIcon", <><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></>);
export const CopyIcon = outline("CopyIcon", <><rect x="8" y="8" width="14" height="14" rx="2" /><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" /></>);
export const DownloadIcon = outline("DownloadIcon", <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4m4-5 5 5 5-5M12 15V3" />);
/** An arc that turns: give it `animate-spin motion-reduce:animate-none`. */
export const SpinnerIcon = outline("SpinnerIcon", <path d="M21 12a9 9 0 1 1-6.22-8.56" />);
export const QuestionIcon = outline("QuestionIcon", <><circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01" /></>);
export const WarningIcon = outline("WarningIcon", <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4M12 17h.01" />);
export const LayersIcon = outline(
  "LayersIcon",
  <path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83zM2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17" />,
);
export const ArrowTurnDownIcon = outline("ArrowTurnDownIcon", <path d="m10 15 5 5 5-5M4 4h7a4 4 0 0 1 4 4v12" />);
export const HalfCircleIcon = outline("HalfCircleIcon", <><circle cx="12" cy="12" r="10" /><path d="M12 18a6 6 0 0 0 0-12z" /></>);
export const BookIcon = outline(
  "BookIcon",
  <path d="M12 7v14M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />,
);
export const HistoryIcon = outline("HistoryIcon", <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5M12 7v5l4 2" />);
export const CircleIcon = outline("CircleIcon", <circle cx="12" cy="12" r="10" />);
export const CircleDotIcon = outline("CircleDotIcon", <><circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="3" fill="currentColor" /></>);
export const FileTextIcon = outline(
  "FileTextIcon",
  <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7zM14 2v4a2 2 0 0 0 2 2h4M10 9H8M16 13H8M16 17H8" />,
);
export const QuoteIcon = outline(
  "QuoteIcon",
  <path d="M16 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2zM5 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z" />,
);
export const StopIcon = outline("StopIcon", <rect x="6" y="6" width="12" height="12" rx="2" />);
export const UnplugIcon = outline(
  "UnplugIcon",
  <path d="m19 5 3-3M2 22l3-3M6.3 20.3a2.4 2.4 0 0 0 3.4 0L12 18l-6-6-2.3 2.3a2.4 2.4 0 0 0 0 3.4zM7.5 13.5 10 11M10.5 16.5 13 14m-1-8 6 6 2.3-2.3a2.4 2.4 0 0 0 0-3.4l-2.6-2.6a2.4 2.4 0 0 0-3.4 0z" />,
);

/** Every glyph of the outline set, by name. */
export const OUTLINE_ICONS = {
  PlusIcon, ArrowUpIcon, ArrowRightIcon, CloseIcon, ChevronDownIcon, ChevronUpIcon, ChevronRightIcon,
  CheckIcon, RetryIcon, PencilIcon, UserIcon, SearchIcon, CopyIcon, DownloadIcon,
  SpinnerIcon, QuestionIcon, WarningIcon, LayersIcon, ArrowTurnDownIcon, HalfCircleIcon, BookIcon,
  HistoryIcon, CircleIcon, CircleDotIcon, FileTextIcon, QuoteIcon, StopIcon, UnplugIcon,
};
