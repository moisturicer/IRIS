import { cn } from "@/lib/utils";
import type { ClearanceStripEntry, ClearanceStripKind } from "@/types/records";

/**
 * Tone and icon per kind, and nothing else: every *word* on the strip --
 * office, state, the version a clearance was kept from or reset by -- is the
 * server's (IR-374 invariant 15). The strip never works out which clearances a
 * resubmission kept; it prints what `clearance_strip` says (IR-1083).
 *
 * Exhaustive, so a kind the server starts sending fails `tsc` until it is
 * given a look here, rather than rendering unstyled. The tones follow the
 * shared ones (`statusTones`, IR-1290): kept and cleared are green, a review in
 * progress is amber, an unclaimed one waits in stone, and an asked-for revision
 * or a negative outcome needs someone, in maroon. So a resubmission that kept
 * two offices and reset one reads green, amber, green at a glance.
 */
const KIND_META: Record<ClearanceStripKind, { icon: string; tone: string }> = {
  // The thesis contribution: the shield the tracker's *Preserved* badge wears.
  kept:        { icon: "fa-shield-halved", tone: "text-cleared" },
  cleared:     { icon: "fa-check",         tone: "text-cleared" },
  reviewing:   { icon: "fa-hourglass-half", tone: "text-review" },
  unclaimed:   { icon: "fa-inbox",         tone: "text-stone-700" },
  revision:    { icon: "fa-rotate-left",   tone: "text-brand" },
  not_cleared: { icon: "fa-ban",           tone: "text-brand" },
};

interface ClearanceStripProps {
  /** Null or absent on a response that predates the field: nothing is drawn (F1). */
  entries?: ClearanceStripEntry[] | null;
  /**
   * One office per line instead of a wrapping row, for a phone card whose
   * entries carry a note ("Kept from v1") too long to share a line (IR-1291).
   */
  stacked?: boolean;
  className?: string;
}

/**
 * One line per specialist office on a record -- "ITSO · Cleared · Kept from
 * v1", "IERC · Reviewing v2 · Reset by v2" -- compact enough for a list row
 * and the same on every list that names the record: My Reviews, the office
 * console, My Library, and the tracker inside the record (IR-1083, audit spec
 * §4.4). Draws nothing when the server names no office.
 *
 * Colour and icon are never the only signal: each entry carries its words.
 */
export function ClearanceStrip({ entries, stacked = false, className }: ClearanceStripProps) {
  if (!Array.isArray(entries) || entries.length === 0) return null;

  return (
    <ul
      aria-label="Clearances"
      className={cn(
        "flex gap-y-1 text-label",
        stacked ? "flex-col items-start" : "flex-wrap items-center gap-x-4",
        className,
      )}
    >
      {entries.map((entry) => {
        const meta = KIND_META[entry.kind];
        return (
          <li key={`${entry.party}:${entry.kind}`} className={cn("inline-flex items-center gap-1.5 font-semibold", meta.tone)}>
            <i className={cn("fas text-3xs", meta.icon)} aria-hidden />
            <span>
              {entry.label}
              <span className="sr-only">:</span>
              {" "}
              {entry.text}
              {entry.note && <span className="font-normal text-stone-600"> · {entry.note}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Whether a strip has anything to draw, for a card that would otherwise reserve
 * a footer for it. Tolerates a response without the field.
 */
export function hasStrip(entries?: ClearanceStripEntry[] | null): entries is ClearanceStripEntry[] {
  return Array.isArray(entries) && entries.length > 0;
}
